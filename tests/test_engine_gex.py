# SPDX-License-Identifier: Apache-2.0
"""Acceptance: fixture GEX matches the expected numbers within 1 USD."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from gex_scanner.adapters.fixtures import load_chain_file
from gex_scanner.config import GEX_UNIT
from gex_scanner.engine.gex import compute_symbol_gex
from tests.helpers import FIXTURES, assert_within_unit

ROOT = Path(__file__).resolve().parents[1]


def _expected(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))["expected"]


def _result(name: str):
    return compute_symbol_gex(load_chain_file(FIXTURES / name))


def test_spy_contract_and_strike_gex_match_fixture_expected() -> None:
    expected = _expected("spy_chain.json")
    result = _result("spy_chain.json")
    by_symbol = {row.occ_symbol: row for row in result.contracts}
    assert set(by_symbol) == {row["occ_symbol"] for row in expected["contracts"]}
    for row in expected["contracts"]:
        actual = by_symbol[row["occ_symbol"]]
        assert_within_unit(actual.gex_unsigned, row["gex_unsigned"])
        assert_within_unit(actual.gex_signed, row["gex_signed"])
    assert [strike.strike for strike in result.strikes] == [
        row["strike"] for row in expected["strikes"]
    ]
    for actual, row in zip(result.strikes, expected["strikes"], strict=True):
        assert actual.strike == row["strike"]
        assert_within_unit(actual.call_gex, row["call_gex"])
        assert_within_unit(actual.put_gex, row["put_gex"])
        assert_within_unit(actual.net_gex, row["net_gex"])
        assert_within_unit(actual.gross_gex, row["gross_gex"])
    assert_within_unit(result.net_gex, expected["net_gex"])
    assert_within_unit(result.book_signed_net, expected["book_signed_net"])
    assert_within_unit(result.book_zero_dte_signed_net, expected["book_zero_dte_signed_net"])
    assert_within_unit(result.book_gross, expected["book_gross"])
    assert_within_unit(result.book_zero_dte_gross, expected["book_zero_dte_gross"])
    assert result.zero_dte_abs_net_share == pytest.approx(
        abs(expected["book_zero_dte_signed_net"]) / abs(expected["book_signed_net"])
    )
    assert result.zero_dte_gross_share == pytest.approx(
        expected["book_zero_dte_gross"] / expected["book_gross"]
    )


def test_spx_contract_and_strike_gex_match_fixture_expected() -> None:
    expected = _expected("spx_chain.json")
    result = _result("spx_chain.json")
    by_symbol = {row.occ_symbol: row for row in result.contracts}
    for row in expected["contracts"]:
        actual = by_symbol[row["occ_symbol"]]
        assert_within_unit(actual.gex_unsigned, row["gex_unsigned"])
        assert_within_unit(actual.gex_signed, row["gex_signed"])
    for actual, row in zip(result.strikes, expected["strikes"], strict=True):
        assert_within_unit(actual.net_gex, row["net_gex"])
        assert_within_unit(actual.call_gex, row["call_gex"])
        assert_within_unit(actual.put_gex, row["put_gex"])
    assert_within_unit(result.net_gex, expected["net_gex"])


def test_all_view_keeps_0dte_contracts() -> None:
    result = _result("spy_chain.json")
    zero_dte = [row.occ_symbol for row in result.contracts if row.dte == 0]
    assert "SPY261113C00500000" in zero_dte
    assert "SPY261113P00490000" in zero_dte


def test_result_states_unit_and_disclaimer() -> None:
    result = _result("spy_chain.json")
    assert result.unit == GEX_UNIT
    assert result.disclaimer == (
        "Estimated dealer GEX under the call_pos_put_neg sign convention. "
        "Not actual market-maker positions."
    )


def test_engine_does_not_hardcode_multiplier_100() -> None:
    source = (ROOT / "src" / "gex_scanner" / "engine" / "gex.py").read_text(encoding="utf-8")
    assert "* 100" not in source
    assert "*100" not in source
