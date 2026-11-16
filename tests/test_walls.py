# SPDX-License-Identifier: Apache-2.0
"""Walls are unsigned side maxima and are not clamped around spot."""

from __future__ import annotations

import json

from gex_scanner.adapters.fixtures import load_chain_file
from gex_scanner.engine.gex import compute_symbol_gex
from tests.helpers import FIXTURES, assert_within_unit, make_contract, make_snapshot


def _expected(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))["expected"]


def test_spy_walls_match_fixture() -> None:
    expected = _expected("spy_chain.json")
    result = compute_symbol_gex(load_chain_file(FIXTURES / "spy_chain.json"))
    assert result.call_wall is not None
    assert result.put_wall is not None
    assert result.gross_magnet is not None
    assert result.call_wall.strike == expected["call_wall"]["strike"]
    assert result.call_wall.spot_side == expected["call_wall"]["spot_side"]
    assert_within_unit(result.call_wall.gex, expected["call_wall"]["gex"])
    assert result.put_wall.strike == expected["put_wall"]["strike"]
    assert result.put_wall.spot_side == expected["put_wall"]["spot_side"]
    assert_within_unit(result.put_wall.gex, expected["put_wall"]["gex"])
    assert result.gross_magnet.strike == expected["gross_magnet"]["strike"]
    assert_within_unit(result.gross_magnet.gex, expected["gross_magnet"]["gex"])


def test_spx_walls_both_above_spot_are_not_clamped() -> None:
    expected = _expected("spx_chain.json")
    snapshot = load_chain_file(FIXTURES / "spx_chain.json")
    result = compute_symbol_gex(snapshot)
    assert result.call_wall is not None
    assert result.put_wall is not None
    assert result.call_wall.strike == expected["call_wall"]["strike"]
    assert result.put_wall.strike == expected["put_wall"]["strike"]
    assert result.call_wall.strike > snapshot.spot
    assert result.put_wall.strike > snapshot.spot
    assert result.call_wall.spot_side == "above"
    assert result.put_wall.spot_side == "above"
    assert result.call_wall.strike != result.put_wall.strike


def test_tie_breaks_toward_spot_then_lower_strike() -> None:
    nearer = compute_symbol_gex(
        make_snapshot(
            [
                make_contract(occ_symbol="C90", strike=90, gamma=0.01, open_interest=10),
                make_contract(occ_symbol="C110", strike=110, gamma=0.01, open_interest=10),
            ],
            spot=105,
        )
    )
    assert nearer.call_wall is not None
    assert nearer.call_wall.strike == 110

    lower = compute_symbol_gex(
        make_snapshot(
            [
                make_contract(occ_symbol="C90", strike=90, gamma=0.01, open_interest=10),
                make_contract(occ_symbol="C110", strike=110, gamma=0.01, open_interest=10),
            ],
            spot=100,
        )
    )
    assert lower.call_wall is not None
    assert lower.call_wall.strike == 90


def test_missing_side_has_no_wall() -> None:
    result = compute_symbol_gex(
        make_snapshot([make_contract(right="call", gamma=0.02, open_interest=10)])
    )
    assert result.call_wall is not None
    assert result.put_wall is None
