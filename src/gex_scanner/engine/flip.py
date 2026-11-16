# SPDX-License-Identifier: Apache-2.0
"""Zero-gamma level by repricing, not by scanning listed strikes.

At each hypothetical spot S, gamma and the S^2 * 0.01 scale are both
evaluated at S. Dealer sign matches the GEX engine. If Black-Scholes gamma
at the snapshot spot disagrees with the vendor gamma by more than the
configured tolerance, that one grid node uses the vendor gamma and the
residual is kept. Off-spot nodes always use Black-Scholes.
"""

from __future__ import annotations

from gex_scanner.config import DAY_COUNT, EngineConfig, disclaimer_for
from gex_scanner.engine.bs import bsm_gamma
from gex_scanner.engine.filters import in_expiry_filter
from gex_scanner.engine.gex import dealer_sign_factor, unsigned_gex
from gex_scanner.engine.quality import assess_contract
from gex_scanner.types import (
    ChainSnapshot,
    Contract,
    FlipCrossing,
    FlipResult,
    GammaResidual,
)

# Re-exported so callers do not import the constant from two places.
__all__ = ["DAY_COUNT", "compute_flip"]


def time_to_expiry(contract: Contract, config: EngineConfig) -> float | None:
    """ACT/365 year fraction held fixed for the whole grid.

    An explicit ``time_years`` wins. Otherwise T = dte / 365. DTE 0 has no
    session clock here, so it uses ``zero_dte_time_years`` (default one
    calendar day). A non-positive result cannot be repriced.
    """

    if contract.time_years is not None:
        years = contract.time_years
    elif contract.dte > 0:
        years = contract.dte / 365.0
    else:
        years = config.zero_dte_time_years
    if years <= 0:
        return None
    return years


def _yield_for(contract: Contract, config: EngineConfig) -> float:
    if contract.dividend_yield is not None:
        return contract.dividend_yield
    return config.dividend_yield


def _grid(spot: float, band: float, points: int) -> list[float]:
    low = spot * (1.0 - band)
    high = spot * (1.0 + band)
    step = (high - low) / (points - 1)
    spots = [low + index * step for index in range(points)]
    # Odd point counts put the snapshot spot on the center node. Force that
    # node to the exact spot so the curve can be compared with the engine.
    spots[points // 2] = spot
    return spots


def _gamma_disagrees(vendor: float, bs_gamma: float, config: EngineConfig) -> bool:
    limit = max(config.gamma_abs_tolerance, config.gamma_rel_tolerance * abs(vendor))
    return abs(bs_gamma - vendor) > limit


def _crossings(spots: list[float], nets: list[float], dust: float) -> list[FlipCrossing]:
    found: list[FlipCrossing] = []

    def _append(spot: float, left: float, right: float) -> None:
        if found and found[-1].spot == spot:
            return
        found.append(FlipCrossing(spot=spot, gex_left=left, gex_right=right))

    def _quiet(value: float) -> bool:
        return abs(value) <= dust

    for index in range(len(spots) - 1):
        left_gex = nets[index]
        right_gex = nets[index + 1]
        if _quiet(left_gex) and _quiet(right_gex):
            continue
        if _quiet(left_gex):
            if index == 0 or not _quiet(nets[index - 1]):
                _append(spots[index], left_gex, right_gex)
            continue
        if _quiet(right_gex):
            continue
        if left_gex * right_gex < 0.0:
            weight = (0.0 - left_gex) / (right_gex - left_gex)
            crossed = spots[index] + (spots[index + 1] - spots[index]) * weight
            _append(crossed, left_gex, right_gex)
    if _quiet(nets[-1]) and not _quiet(nets[-2]):
        _append(spots[-1], nets[-2], nets[-1])
    return found


def _primary(crossings: list[FlipCrossing], spot: float) -> float | None:
    if not crossings:
        return None
    # Nearest to the snapshot spot. An exact distance tie keeps the lower spot.
    return min(crossings, key=lambda item: (abs(item.spot - spot), item.spot)).spot


def compute_flip(snapshot: ChainSnapshot, config: EngineConfig | None = None) -> FlipResult:
    """Reprice the active expiry view and interpolate net-GEX zeros.

    Returns every in-band crossing. ``primary_flip`` is the one nearest the
    snapshot spot. When nothing crosses, ``primary_flip`` is None and
    ``no_crossing_in_band`` is true. No strike is substituted for a missing flip.
    """

    if config is None:
        config = EngineConfig()
    if snapshot.spot <= 0:
        raise ValueError("spot must be positive")

    spots = _grid(snapshot.spot, config.flip_band, config.flip_grid_points)
    included: list[tuple[Contract, float, float, float, float]] = []
    skipped: list[tuple[str, str]] = []
    residuals: list[GammaResidual] = []

    for contract in snapshot.contracts:
        assessment = assess_contract(contract, config, captured_at_utc=snapshot.captured_at_utc)
        if not assessment.include or not in_expiry_filter(contract, config):
            continue
        assert contract.gamma is not None
        assert contract.open_interest is not None
        if contract.iv is None:
            skipped.append((contract.occ_symbol, "missing_iv"))
            continue
        if contract.iv <= 0:
            skipped.append((contract.occ_symbol, "non_positive_iv"))
            continue
        years = time_to_expiry(contract, config)
        if years is None:
            skipped.append((contract.occ_symbol, "invalid_time"))
            continue
        dividend = _yield_for(contract, config)
        try:
            model_gamma = bsm_gamma(
                snapshot.spot,
                contract.strike,
                config.risk_free_rate,
                dividend,
                contract.iv,
                years,
            )
        except ValueError:
            skipped.append((contract.occ_symbol, "bsm_undefined"))
            continue
        vendor = abs(contract.gamma)
        pin = _gamma_disagrees(vendor, model_gamma, config)
        residuals.append(
            GammaResidual(
                occ_symbol=contract.occ_symbol,
                vendor_gamma=vendor,
                bs_gamma=model_gamma,
                residual=model_gamma - vendor,
                used_vendor_gamma_at_spot=pin,
            )
        )
        included.append((contract, years, dividend, vendor if pin else model_gamma, contract.iv))

    nets = [0.0] * len(spots)
    vendor_net = 0.0
    spot_index = config.flip_grid_points // 2
    for contract, years, dividend, spot_gamma, sigma in included:
        assert contract.open_interest is not None
        sign = dealer_sign_factor(contract, config)
        for index, hypothetical in enumerate(spots):
            if index == spot_index:
                gamma = spot_gamma
            else:
                gamma = bsm_gamma(
                    hypothetical,
                    contract.strike,
                    config.risk_free_rate,
                    dividend,
                    sigma,
                    years,
                )
            signed = (
                sign
                * gamma
                * contract.open_interest
                * contract.multiplier
                * (hypothetical * hypothetical * 0.01)
            )
            nets[index] += signed
        vendor_net += sign * unsigned_gex(
            abs(contract.gamma) if contract.gamma is not None else 0.0,
            contract.open_interest,
            contract.multiplier,
            snapshot.spot,
        )

    crossings = _crossings(spots, nets, config.flip_dust)
    primary = _primary(crossings, snapshot.spot)
    return FlipResult(
        underlying=snapshot.underlying,
        snapshot_spot=snapshot.spot,
        expiry_filter=config.expiry_filter.value,
        band=config.flip_band,
        band_low=spots[0],
        band_high=spots[-1],
        grid_points=config.flip_grid_points,
        day_count=DAY_COUNT,
        risk_free_rate=config.risk_free_rate,
        dividend_yield=config.dividend_yield,
        crossings=tuple(crossings),
        primary_flip=primary,
        no_crossing_in_band=not crossings,
        curve_net_at_spot=nets[spot_index],
        vendor_net_at_spot=vendor_net,
        residuals=tuple(residuals),
        skipped=tuple(skipped),
        grid_spots=tuple(spots),
        grid_net=tuple(nets),
        unit="USD of estimated dealer delta change per 1% move",
        disclaimer=disclaimer_for(config.dealer_sign),
    )
