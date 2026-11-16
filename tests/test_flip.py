# SPDX-License-Identifier: Apache-2.0
"""Flip repricing and expiry views that can disagree.

The closed-form root and the neighbor-node gamma are written out in this
file. They do not call the engine's Black-Scholes function.
"""

from __future__ import annotations

import math

import pytest

from gex_scanner.config import EngineConfig, ExpiryFilter
from gex_scanner.engine.flip import compute_flip
from gex_scanner.engine.gex import compute_symbol_gex
from tests.helpers import TOLERANCE, make_contract, make_snapshot

# Half of the default grid step when spot is 100 (step = 0.10).
TICK_TOLERANCE = 0.05
SIGMA = 0.20
TIME = 30 / 365
SPOT = 100.0


def reference_bsm_gamma(
    spot: float,
    strike: float,
    rate: float,
    dividend_yield: float,
    sigma: float,
    time_years: float,
) -> float:
    """Black-Scholes-Merton gamma, copied here so the engine is not the oracle."""

    vol_sqrt_t = sigma * math.sqrt(time_years)
    d1 = (
        math.log(spot / strike) + (rate - dividend_yield + 0.5 * sigma * sigma) * time_years
    ) / vol_sqrt_t
    density = math.exp(-0.5 * d1 * d1) / math.sqrt(2.0 * math.pi)
    return math.exp(-dividend_yield * time_years) * density / (spot * sigma * math.sqrt(time_years))


def _priced(
    occ: str,
    right: str,
    strike: float,
    open_interest: float,
    *,
    dte: int = 30,
    time_years: float = TIME,
    iv: float | None = SIGMA,
    gamma: float | None = None,
    multiplier: float = 100.0,
) -> object:
    model = None
    if iv is not None and iv > 0 and time_years > 0:
        model = reference_bsm_gamma(SPOT, strike, 0.0, 0.0, iv, time_years)
    return make_contract(
        occ_symbol=occ,
        right=right,
        strike=strike,
        open_interest=open_interest,
        dte=dte,
        expiry_kind="weekly",
        multiplier=multiplier,
        iv=iv,
        gamma=model if gamma is None else gamma,
        time_years=time_years,
    )


def test_closed_form_crossing_is_within_a_tick_and_matches_spot_gex() -> None:
    call_strike = 90.0
    put_strike = 110.0
    analytical = math.sqrt(call_strike * put_strike) * math.exp(-0.5 * SIGMA * SIGMA * TIME)
    snapshot = make_snapshot(
        [
            _priced("C90", "call", call_strike, 10),
            _priced("P110", "put", put_strike, 10),
        ]
    )
    flip = compute_flip(snapshot)
    engine = compute_symbol_gex(snapshot)

    assert flip.primary_flip is not None
    assert abs(flip.primary_flip - analytical) <= TICK_TOLERANCE
    assert len(flip.crossings) == 1
    assert flip.no_crossing_in_band is False
    for strike in (call_strike, put_strike, SPOT):
        assert abs(flip.primary_flip - strike) > 0.5
    assert abs(flip.curve_net_at_spot - engine.net_gex) <= TOLERANCE
    assert abs(flip.vendor_net_at_spot - engine.net_gex) <= TOLERANCE
    assert flip.skipped == ()
    assert flip.day_count == "ACT/365"
    assert flip.band == 0.15
    assert flip.grid_spots[len(flip.grid_spots) // 2] == SPOT
    assert all(item.used_vendor_gamma_at_spot is False for item in flip.residuals)


def test_equal_scaling_does_not_move_the_closed_form_flip() -> None:
    base = make_snapshot(
        [
            _priced("C90", "call", 90.0, 10),
            _priced("P110", "put", 110.0, 10),
        ]
    )
    scaled = make_snapshot(
        [
            _priced("C90", "call", 90.0, 40, multiplier=250),
            _priced("P110", "put", 110.0, 40, multiplier=250),
        ]
    )
    base_flip = compute_flip(base)
    scaled_flip = compute_flip(scaled)
    assert base_flip.primary_flip is not None
    assert scaled_flip.primary_flip is not None
    assert scaled_flip.primary_flip == pytest.approx(base_flip.primary_flip, abs=1e-9)


def test_two_crossings_are_both_returned() -> None:
    # Independent scan of this book (call 90 x 25, put 100 x 40, call 110 x 25)
    # changes sign once near 93.5 and once near 106.4, both inside ±15%.
    snapshot = make_snapshot(
        [
            _priced("C90", "call", 90.0, 25),
            _priced("P100", "put", 100.0, 40),
            _priced("C110", "call", 110.0, 25),
        ]
    )
    flip = compute_flip(snapshot)
    spots = sorted(item.spot for item in flip.crossings)
    assert len(spots) == 2
    assert 92.0 < spots[0] < 95.0
    assert 105.0 < spots[1] < 108.0
    assert flip.primary_flip == min(spots, key=lambda spot: (abs(spot - SPOT), spot))
    for strike in (90.0, 100.0, 110.0):
        assert all(abs(spot - strike) > 0.5 for spot in spots)
    assert flip.no_crossing_in_band is False


def test_no_crossing_in_band_does_not_invent_a_strike() -> None:
    snapshot = make_snapshot(
        [
            _priced("C90", "call", 90.0, 10),
            _priced("C110", "call", 110.0, 10),
        ]
    )
    flip = compute_flip(snapshot)
    assert flip.crossings == ()
    assert flip.primary_flip is None
    assert flip.no_crossing_in_band is True
    assert flip.curve_net_at_spot > 0


def test_spot_node_uses_vendor_gamma_when_black_scholes_disagrees() -> None:
    time_years = TIME
    model = reference_bsm_gamma(SPOT, 100.0, 0.0, 0.0, SIGMA, time_years)
    vendor = model * 3.0
    snapshot = make_snapshot(
        [_priced("C100", "call", 100.0, 10, gamma=vendor, time_years=time_years)]
    )
    flip = compute_flip(snapshot)
    engine = compute_symbol_gex(snapshot)

    assert len(flip.residuals) == 1
    residual = flip.residuals[0]
    assert residual.used_vendor_gamma_at_spot is True
    assert residual.residual == pytest.approx(model - vendor)
    assert abs(flip.curve_net_at_spot - engine.net_gex) <= TOLERANCE

    center = len(flip.grid_spots) // 2
    neighbor = flip.grid_spots[center + 1]
    expected_gamma = reference_bsm_gamma(neighbor, 100.0, 0.0, 0.0, SIGMA, time_years)
    expected_net = expected_gamma * 10.0 * 100.0 * neighbor * neighbor * 0.01
    assert flip.grid_net[center + 1] == pytest.approx(expected_net, rel=1e-9)
    # The pinned node is the vendor print, not the model gamma.
    vendor_net = vendor * 10.0 * 100.0 * SPOT * SPOT * 0.01
    assert flip.grid_net[center] == pytest.approx(vendor_net, rel=1e-9)
    assert flip.grid_net[center] != pytest.approx(vendor_net / 3.0, rel=1e-6)


def test_missing_iv_is_skipped_instead_of_booked_as_zero_gamma() -> None:
    usable = _priced("C90", "call", 90.0, 10)
    blind = make_contract(
        occ_symbol="NOIV",
        right="call",
        strike=100.0,
        open_interest=50.0,
        gamma=0.05,
        iv=None,
        dte=30,
        time_years=TIME,
    )
    snapshot = make_snapshot([usable, blind])
    flip = compute_flip(snapshot)
    full = compute_symbol_gex(snapshot)
    only_usable = compute_symbol_gex(make_snapshot([usable]))

    assert ("NOIV", "missing_iv") in flip.skipped
    assert abs(flip.curve_net_at_spot - only_usable.net_gex) <= TOLERANCE
    assert abs(flip.curve_net_at_spot - full.net_gex) > TOLERANCE


def test_zero_dte_walls_can_differ_from_all_expiry_walls() -> None:
    # Unsigned GEX at spot 100 uses scale 100. The far dated strikes dominate
    # the all-expiry walls. The 0DTE view only sees 100 and 90.
    contracts = [
        make_contract(
            occ_symbol="C0",
            right="call",
            strike=100.0,
            gamma=0.01,
            open_interest=100.0,
            dte=0,
            iv=0.2,
        ),
        make_contract(
            occ_symbol="P0",
            right="put",
            strike=90.0,
            gamma=0.01,
            open_interest=100.0,
            dte=0,
            iv=0.2,
        ),
        make_contract(
            occ_symbol="C20",
            right="call",
            strike=120.0,
            gamma=0.05,
            open_interest=500.0,
            dte=20,
            iv=0.2,
            time_years=20 / 365,
        ),
        make_contract(
            occ_symbol="P20",
            right="put",
            strike=70.0,
            gamma=0.05,
            open_interest=500.0,
            dte=20,
            iv=0.2,
            time_years=20 / 365,
        ),
    ]
    snapshot = make_snapshot(contracts, spot=SPOT)
    zero = compute_symbol_gex(snapshot, EngineConfig(expiry_filter=ExpiryFilter.ZERO_DTE))
    everything = compute_symbol_gex(snapshot, EngineConfig(expiry_filter=ExpiryFilter.ALL))

    assert zero.call_wall is not None and everything.call_wall is not None
    assert zero.put_wall is not None and everything.put_wall is not None
    assert zero.call_wall.strike == 100.0
    assert everything.call_wall.strike == 120.0
    assert zero.put_wall.strike == 90.0
    assert everything.put_wall.strike == 70.0
    assert zero.call_wall.gex == pytest.approx(10_000.0)
    assert everything.call_wall.gex == pytest.approx(250_000.0)


def test_zero_dte_flip_view_can_differ_from_all_expiries() -> None:
    snapshot = make_snapshot(
        [
            _priced("C0", "call", 100.0, 10, dte=0, time_years=1 / 365),
            _priced("C90", "call", 90.0, 10, dte=30),
            _priced("P110", "put", 110.0, 10, dte=30),
        ]
    )
    zero = compute_flip(snapshot, EngineConfig(expiry_filter=ExpiryFilter.ZERO_DTE))
    everything = compute_flip(snapshot, EngineConfig(expiry_filter=ExpiryFilter.ALL))
    assert zero.primary_flip is None
    assert zero.no_crossing_in_band is True
    assert everything.primary_flip is not None
    assert everything.no_crossing_in_band is False


def test_second_order_stays_refused() -> None:
    with pytest.raises(ValueError, match="enable_second_order"):
        EngineConfig(enable_second_order=True)
