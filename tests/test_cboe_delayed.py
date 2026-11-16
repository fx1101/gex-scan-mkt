# SPDX-License-Identifier: Apache-2.0
"""Recorded Cboe payloads. These tests do not open a socket."""

from __future__ import annotations

import json
from datetime import UTC
from pathlib import Path

import pytest
from scripts.cboe_snapshot import main

from gex_scanner.adapters.cboe_delayed import (
    CboeDelayedProvider,
    delayed_quote_url,
    fetch_delayed_quotes,
    parse_cboe_payload,
)
from gex_scanner.adapters.fixtures import read_raw_cache, write_raw_cache

FIXTURES = Path(__file__).parent / "fixtures" / "recorded"


def test_recorded_nok_payload_parses_without_network() -> None:
    path = FIXTURES / "cboe_nok_delayed.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    snapshot = parse_cboe_payload(path.read_text(encoding="utf-8"))
    by_symbol = {item.occ_symbol: item for item in snapshot.contracts}

    assert snapshot.vendor == "cboe_delayed"
    assert snapshot.underlying == "NOK"
    assert snapshot.spot == raw["data"]["current_price"]
    assert snapshot.spot_field == "current_price"
    assert snapshot.captured_at_utc == snapshot.captured_at_utc.astimezone(UTC)
    assert snapshot.captured_at_utc.isoformat() == "2026-11-16T00:29:44+00:00"
    assert snapshot.session_key == "asia_watch"
    assert snapshot.raw_json is not None
    assert len(snapshot.contracts) == len(raw["data"]["options"])
    sample = by_symbol["NOK261120C00007500"]
    source = next(item for item in raw["data"]["options"] if item["option"] == sample.occ_symbol)
    assert "multiplier" not in source
    assert sample.multiplier == 100.0
    assert "multiplier_not_in_payload" in sample.provider_flags
    assert sample.right == "call"
    assert sample.strike == 7.5
    assert sample.gamma == source["gamma"]
    assert sample.open_interest == source["open_interest"]
    assert sample.iv == source["iv"]
    assert sample.rho == source["rho"]
    assert sample.dte == 5
    assert sample.exercise_style == "american"
    assert sample.quote_time is not None
    assert sample.quote_time.utcoffset() is not None


def test_recorded_spx_payload_uses_the_index_symbol() -> None:
    path = FIXTURES / "cboe_spx_delayed.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    snapshot = parse_cboe_payload(path.read_text(encoding="utf-8"))
    contract = snapshot.contracts[0]
    assert raw["symbol"] == "_SPX"
    assert raw["data"]["symbol"] == "^SPX"
    assert snapshot.underlying == "SPX"
    assert snapshot.spot == raw["data"]["current_price"]
    assert contract.occ_symbol == "SPX261120C07560000"
    assert contract.strike == 7560.0
    assert contract.exercise_style == "european"
    assert contract.settlement == "cash"
    assert contract.gamma == raw["data"]["options"][0]["gamma"]


def test_raw_cache_round_trip(tmp_path: Path) -> None:
    path = FIXTURES / "cboe_nok_delayed.json"
    snapshot = parse_cboe_payload(path.read_text(encoding="utf-8"))
    cached = write_raw_cache(snapshot, tmp_path)
    assert cached.name.endswith(".json.gz")
    assert read_raw_cache(cached) == snapshot.raw_json


def test_live_fetch_is_refused_without_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(*_args, **_kwargs):
        raise AssertionError("urlopen was called")

    monkeypatch.setattr("urllib.request.urlopen", _boom)
    with pytest.raises(RuntimeError, match="--network"):
        fetch_delayed_quotes("NOK", network=False)
    with pytest.raises(RuntimeError, match="--network"):
        CboeDelayedProvider().get_chain("NOK")


def test_script_parses_a_fixture_and_refuses_a_download() -> None:
    fixture = FIXTURES / "cboe_nok_delayed.json"
    assert main(["--fixture", str(fixture)]) == 0
    assert main(["NOK"]) == 2


def test_index_url_uses_an_underscore_and_equity_does_not() -> None:
    assert delayed_quote_url("SPX").endswith("/_SPX.json")
    assert delayed_quote_url("^SPX").endswith("/_SPX.json")
    assert delayed_quote_url("NOK").endswith("/NOK.json")
