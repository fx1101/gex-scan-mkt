# SPDX-License-Identifier: Apache-2.0
"""Fixture provider keeps the raw payload and does not use the network."""

from __future__ import annotations

from datetime import UTC
from zoneinfo import ZoneInfo

from gex_scanner.adapters.fixtures import (
    FixtureProvider,
    load_chain_file,
    read_raw_cache,
    write_raw_cache,
)
from tests.helpers import FIXTURES


def test_raw_payload_roundtrips_through_gzip_cache(tmp_path) -> None:
    snapshot = load_chain_file(FIXTURES / "spy_chain.json")
    assert snapshot.raw_json is not None
    assert "expected" in snapshot.raw_json
    path = write_raw_cache(snapshot, tmp_path)
    assert path == tmp_path / "fixture" / "SPY" / "spy-sample-001.json.gz"
    assert read_raw_cache(path) == snapshot.raw_json


def test_provider_selects_underlying_from_a_directory() -> None:
    provider = FixtureProvider(FIXTURES)
    spy = provider.get_chain("SPY")
    spx = provider.get_chain("SPX", snapshot_id="spx-sample-001")
    assert spy.underlying == "SPY"
    assert spx.snapshot_id == "spx-sample-001"
    assert spy.futures == ()


def test_captured_at_is_stored_in_utc_and_chicago() -> None:
    snapshot = load_chain_file(FIXTURES / "spy_chain.json")
    assert snapshot.captured_at_utc.tzinfo is not None
    assert snapshot.captured_at_utc.astimezone(UTC).hour == 15
    chicago = snapshot.captured_at_ct.astimezone(ZoneInfo("America/Chicago"))
    assert chicago.hour == 9
    assert chicago.tzname() == "CST"
