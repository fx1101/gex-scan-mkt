# SPDX-License-Identifier: Apache-2.0
"""Expiry filters, including a 0DTE view that is separate from all."""

from __future__ import annotations

import json
from datetime import date

from gex_scanner.adapters.fixtures import load_chain_file
from gex_scanner.config import EngineConfig, ExpiryFilter
from gex_scanner.engine.filters import is_monthly, is_third_friday
from gex_scanner.engine.gex import compute_symbol_gex
from tests.conftest import FIXTURES, assert_within_unit, make_contract


def test_spy_filter_nets_match_fixture() -> None:
    payload = json.loads((FIXTURES / "spy_chain.json").read_text(encoding="utf-8"))
    expected = payload["expected"]["filters"]
    snapshot = load_chain_file(FIXTURES / "spy_chain.json")
    cases = {
        ExpiryFilter.ALL: expected["all"],
        ExpiryFilter.ZERO_DTE: expected["0dte"],
        ExpiryFilter.LTE_7D: expected["lte_7d"],
        ExpiryFilter.LTE_30D: expected["lte_30d"],
        ExpiryFilter.MONTHLY: expected["monthly"],
    }
    for filt, net in cases.items():
        result = compute_symbol_gex(snapshot, EngineConfig(expiry_filter=filt))
        assert_within_unit(result.net_gex, net)
    custom = compute_symbol_gex(
        snapshot,
        EngineConfig(
            expiry_filter=ExpiryFilter.CUSTOM,
            custom_expiries=frozenset({date(2026, 12, 3)}),
        ),
    )
    assert_within_unit(custom.net_gex, expected["custom_2026-12-03"])
    assert [row.occ_symbol for row in custom.contracts] == ["SPY261203P00480000"]


def test_0dte_view_differs_from_all_and_all_still_contains_0dte() -> None:
    snapshot = load_chain_file(FIXTURES / "spy_chain.json")
    full = compute_symbol_gex(snapshot, EngineConfig(expiry_filter=ExpiryFilter.ALL))
    zero = compute_symbol_gex(snapshot, EngineConfig(expiry_filter=ExpiryFilter.ZERO_DTE))
    assert full.net_gex != zero.net_gex
    assert any(row.dte == 0 for row in full.contracts)
    assert all(row.dte == 0 for row in zero.contracts)


def test_monthly_filter_has_no_put_wall_on_spy_fixture() -> None:
    snapshot = load_chain_file(FIXTURES / "spy_chain.json")
    result = compute_symbol_gex(snapshot, EngineConfig(expiry_filter=ExpiryFilter.MONTHLY))
    assert result.call_wall is not None
    assert result.call_wall.strike == 520
    assert result.put_wall is None


def test_explicit_weekly_on_third_friday_is_not_monthly() -> None:
    assert is_third_friday(date(2026, 12, 18))
    assert not is_third_friday(date(2026, 11, 13))
    weekly = make_contract(expiry=date(2026, 12, 18), expiry_kind="weekly", dte=32)
    monthly = make_contract(expiry=date(2026, 12, 18), expiry_kind="monthly", dte=32)
    inferred = make_contract(expiry=date(2026, 12, 18), expiry_kind=None, dte=32)
    assert not is_monthly(weekly)
    assert is_monthly(monthly)
    assert is_monthly(inferred)


def test_lte_filters_include_same_day_expiry() -> None:
    snapshot = load_chain_file(FIXTURES / "spy_chain.json")
    week = compute_symbol_gex(snapshot, EngineConfig(expiry_filter=ExpiryFilter.LTE_7D))
    assert any(row.dte == 0 for row in week.contracts)
    assert all(row.dte <= 7 for row in week.contracts)
