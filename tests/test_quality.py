# SPDX-License-Identifier: Apache-2.0
"""Missing greeks, zero OI, and non-standard deliverables."""

from __future__ import annotations

import json

from gex_scanner.adapters.fixtures import load_chain_file
from gex_scanner.config import DealerSign, EngineConfig
from gex_scanner.engine.gex import compute_symbol_gex, unsigned_gex
from tests.helpers import FIXTURES, assert_within_unit, make_contract, make_snapshot


def test_missing_iv_is_flagged_and_still_priced_from_gamma() -> None:
    payload = json.loads((FIXTURES / "missing_iv.json").read_text(encoding="utf-8"))
    expected = payload["expected"]
    result = compute_symbol_gex(load_chain_file(FIXTURES / "missing_iv.json"))
    by_symbol = {row.occ_symbol: row for row in result.contracts}
    for row in expected["contracts"]:
        actual = by_symbol[row["occ_symbol"]]
        assert_within_unit(actual.gex_unsigned, row["gex_unsigned"])
        assert_within_unit(actual.gex_signed, row["gex_signed"])
        for flag in row["flags"]:
            assert flag in actual.flags
    assert_within_unit(result.net_gex, expected["net_gex"])
    excluded = {item.occ_symbol: item.exclusion_reasons for item in result.quality.excluded}
    for row in expected["excluded"]:
        assert row["reasons"][0] in excluded[row["occ_symbol"]]
        assert row["occ_symbol"] not in by_symbol


def test_missing_gamma_is_not_booked_as_a_zero_row() -> None:
    result = compute_symbol_gex(load_chain_file(FIXTURES / "spy_chain.json"))
    symbols = {row.occ_symbol for row in result.contracts}
    assert "SPY261123C00505000" not in symbols
    excluded = {item.occ_symbol: item for item in result.quality.excluded}
    assert "missing_gamma" in excluded["SPY261123C00505000"].exclusion_reasons
    assert all(row.gex_unsigned != 0 or row.open_interest == 0 for row in result.contracts)


def test_zero_oi_is_skipped_unless_debug_flag_is_on() -> None:
    snapshot = load_chain_file(FIXTURES / "spy_chain.json")
    default = compute_symbol_gex(snapshot)
    assert "SPY261113C00505000" not in {row.occ_symbol for row in default.contracts}
    included = compute_symbol_gex(snapshot, EngineConfig(include_zero_oi=True))
    zero = next(row for row in included.contracts if row.occ_symbol == "SPY261113C00505000")
    assert "zero_oi" in zero.flags
    assert_within_unit(zero.gex_signed, 0)


def test_stale_quote_provider_flag_is_a_warning_not_an_exclusion() -> None:
    result = compute_symbol_gex(load_chain_file(FIXTURES / "spy_chain.json"))
    monthly = next(row for row in result.contracts if row.occ_symbol == "SPY261218C00520000")
    assert "stale_quote" in monthly.flags
    warned = {item.occ_symbol for item in result.quality.warnings}
    assert "SPY261218C00520000" in warned


def test_nonstandard_multiplier_is_not_the_naive_100_result() -> None:
    payload = json.loads((FIXTURES / "nonstandard_multiplier.json").read_text(encoding="utf-8"))
    expected = payload["expected"]
    snapshot = load_chain_file(FIXTURES / "nonstandard_multiplier.json")
    default = compute_symbol_gex(snapshot)
    assert_within_unit(default.net_gex, expected["default_net_gex"])
    assert "ADJ261113C00055000" not in {row.occ_symbol for row in default.contracts}
    appendix = {item.occ_symbol for item in default.quality.nonstandard_appendix}
    assert "ADJ261113C00055000" in appendix

    included = compute_symbol_gex(snapshot, EngineConfig(include_nonstandard=True))
    assert_within_unit(included.net_gex, expected["included_nonstandard_net_gex"])
    special = next(row for row in included.contracts if row.occ_symbol == "ADJ261113C00055000")
    assert_within_unit(
        special.gex_unsigned,
        expected["nonstandard_contract"]["gex_unsigned_actual_multiplier"],
    )
    naive = unsigned_gex(gamma=0.1, open_interest=10, multiplier=100, spot=50)
    assert_within_unit(naive, expected["nonstandard_contract"]["gex_unsigned_if_multiplier_100"])
    assert special.gex_unsigned != naive
    assert included.net_gex != expected["naive_both_at_multiplier_100_net_gex"]


def test_flow_signed_does_not_infer_a_sign_from_volume() -> None:
    noisy = make_contract(volume=1_000_000, flow_sign=None, gamma=0.02, open_interest=10)
    snapshot = make_snapshot([noisy])
    result = compute_symbol_gex(snapshot, EngineConfig(dealer_sign=DealerSign.FLOW_SIGNED))
    assert result.contracts == ()
    assert result.quality.excluded[0].exclusion_reasons == ("missing_flow_sign",)

    signed = compute_symbol_gex(
        make_snapshot([make_contract(flow_sign=-1, right="call", gamma=0.02, open_interest=10)]),
        EngineConfig(dealer_sign=DealerSign.FLOW_SIGNED),
    )
    assert signed.net_gex < 0
