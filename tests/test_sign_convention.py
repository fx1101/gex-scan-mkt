# SPDX-License-Identifier: Apache-2.0
"""Changing dealer_sign changes the sign of net GEX."""

from __future__ import annotations

from gex_scanner.config import DealerSign, EngineConfig
from gex_scanner.engine.gex import compute_symbol_gex
from tests.helpers import assert_within_unit, make_contract, make_snapshot


def test_flipping_dealer_sign_flips_net_gex_for_a_symmetric_book() -> None:
    """Identical calls are the symmetric book.

    ``call_pos_put_neg`` signs each call positive. ``dealers_short_both``
    signs each call negative. Net GEX changes sign and keeps its magnitude.
    """

    book = make_snapshot(
        [
            make_contract(occ_symbol="C1", gamma=0.02, open_interest=100, multiplier=100),
            make_contract(
                occ_symbol="C2",
                strike=105,
                gamma=0.02,
                open_interest=100,
                multiplier=100,
            ),
        ]
    )
    positive = compute_symbol_gex(book, EngineConfig(dealer_sign=DealerSign.CALL_POS_PUT_NEG))
    negative = compute_symbol_gex(book, EngineConfig(dealer_sign=DealerSign.DEALERS_SHORT_BOTH))
    assert positive.net_gex > 0
    assert_within_unit(negative.net_gex, -positive.net_gex)
    assert "dealers_short_both" in negative.disclaimer
    assert "call_pos_put_neg" in positive.disclaimer


def test_symmetric_straddle_is_flat_under_the_default_and_short_under_both() -> None:
    call = make_contract(occ_symbol="C", right="call", gamma=0.02, open_interest=100)
    put = make_contract(occ_symbol="P", right="put", gamma=-0.02, open_interest=100, strike=100)
    book = make_snapshot([call, put])
    default = compute_symbol_gex(book, EngineConfig(dealer_sign=DealerSign.CALL_POS_PUT_NEG))
    short = compute_symbol_gex(book, EngineConfig(dealer_sign=DealerSign.DEALERS_SHORT_BOTH))
    assert_within_unit(default.net_gex, 0)
    assert short.net_gex < 0
    assert_within_unit(short.net_gex, -2 * call_leg(default))


def test_puts_stay_negative_under_both_listed_conventions() -> None:
    book = make_snapshot([make_contract(occ_symbol="P", right="put", gamma=0.02, open_interest=50)])
    default = compute_symbol_gex(book, EngineConfig(dealer_sign=DealerSign.CALL_POS_PUT_NEG))
    short = compute_symbol_gex(book, EngineConfig(dealer_sign=DealerSign.DEALERS_SHORT_BOTH))
    assert default.net_gex < 0
    assert_within_unit(short.net_gex, default.net_gex)


def call_leg(result) -> float:
    return next(row.gex_unsigned for row in result.contracts if row.right == "call")
