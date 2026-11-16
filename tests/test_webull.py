# SPDX-License-Identifier: Apache-2.0
"""Webull mapping, batches, limiter, and entitlement errors. No sockets."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from scripts.webull_snapshot import main

from gex_scanner.adapters.webull import (
    EntitlementError,
    RateLimitError,
    TokenBucket,
    WebullConfig,
    classify_status,
    fetch_chain,
    limiters_for,
    probe_capabilities,
    snapshot_batches,
)
from gex_scanner.engine.gex import compute_symbol_gex

FIXTURE = Path(__file__).parent / "fixtures" / "recorded" / "webull_spy_chain.json"
AS_OF = datetime(2026, 11, 16, 15, 0, tzinfo=UTC)


class _Clock:
    def __init__(self) -> None:
        self.t = 0.0
        self.slept: list[float] = []

    def now(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.t += seconds


class _Book:
    """Serves the recorded SPY pages. Counts snapshot batch sizes."""

    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.list_calls: list[dict] = []
        self.batches: list[list[str]] = []
        self.fail_times = 0

    def underlying_snapshot(self, symbol: str) -> dict:
        assert symbol == "SPY"
        return self.payload["underlying_snapshot"]

    def list_contracts(self, params: dict) -> dict:
        self.list_calls.append(dict(params))
        if params.get("pagination_key") == "page-2":
            return self.payload["contract_pages"][1]
        return self.payload["contract_pages"][0]

    def option_snapshots(self, symbols: list[str]) -> list[dict]:
        if self.fail_times:
            self.fail_times -= 1
            raise RateLimitError("HTTP 429", retry_after=0.5)
        self.batches.append(list(symbols))
        wanted = set(symbols)
        return [row for row in self.payload["snapshots"] if row["symbol"] in wanted]


def test_recorded_payload_maps_and_skips_without_network() -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    book = _Book(payload)
    clock = _Clock()
    result = fetch_chain(
        book,
        "SPY",
        as_of=AS_OF,
        config=WebullConfig(),
        now=clock.now,
        sleep=clock.sleep,
        buckets=limiters_for("sandbox"),
    )
    snapshot = result.snapshot
    by_symbol = {item.occ_symbol: item for item in snapshot.contracts}

    assert snapshot.vendor == "webull"
    assert snapshot.spot == 500.0
    assert snapshot.spot_field == "price"
    assert snapshot.session_key == "us_rth"
    assert result.counts.listed == 6
    assert result.counts.quoted == 3
    assert result.counts.skipped == 3
    assert result.counts.batches == 1
    reasons = dict(result.counts.skip_reasons)
    assert reasons["SPY261218C00500000"] == "dte_cap"
    assert reasons["SPY261116C00200000"] == "moneyness"
    assert reasons["SPY261116C00505000"] == "delisting"
    call = by_symbol["SPY261116C00500000"]
    assert call.right == "call"
    assert call.strike == 500.0
    assert call.gamma == 0.02
    assert call.iv == 0.2
    assert call.open_interest == 10.0
    assert call.multiplier == 100.0
    assert call.dte == 0
    assert book.list_calls[0]["strike_price_gte"] == pytest.approx(425.0)
    assert book.list_calls[0]["strike_price_lte"] == pytest.approx(575.0)
    assert "pagination_key" not in book.list_calls[0]
    assert book.list_calls[1]["pagination_key"] == "page-2"
    gex = compute_symbol_gex(snapshot)
    assert gex.net_gex != 0


def test_snapshots_are_batched_at_twenty() -> None:
    symbols = [f"SPY261116C{index:08d}" for index in range(21)]
    groups = snapshot_batches(symbols, 20)
    assert [len(group) for group in groups] == [20, 1]
    with pytest.raises(ValueError, match="20"):
        WebullConfig(snapshot_batch_size=21)


def test_sandbox_bucket_waits_after_thirty_calls() -> None:
    bucket = limiters_for("sandbox").snapshots
    clock = _Clock()
    for _ in range(30):
        bucket.acquire(clock.now, clock.sleep)
    assert clock.slept == []
    bucket.acquire(clock.now, clock.sleep)
    assert clock.slept == [pytest.approx(2.0)]
    assert limiters_for("production").snapshots.capacity == 300
    assert limiters_for("production").contracts.capacity == 60
    assert limiters_for("sandbox").contracts.capacity == 30


def test_http_429_backs_off_and_403_is_an_entitlement_error() -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    book = _Book(payload)
    book.fail_times = 1
    clock = _Clock()
    result = fetch_chain(
        book,
        "SPY",
        as_of=AS_OF,
        now=clock.now,
        sleep=clock.sleep,
        buckets=limiters_for("sandbox"),
    )
    assert result.counts.quoted == 3
    assert 0.5 in clock.slept
    with pytest.raises(EntitlementError, match="OPRA Real-Time Non-display") as caught:
        classify_status(403)
    assert caught.value.http_status == 403
    with pytest.raises(RateLimitError):
        classify_status(429, retry_after=1.0)


def test_capability_report_does_not_mark_an_empty_page_as_covered() -> None:
    pages = {
        "SPX": {"data": [{"symbol": "SPX261220P04200000", "instrument_id": "spx-1"}]},
        "SPXW": {"data": [{"symbol": "SPXW261116C06000000", "instrument_id": "spxw-1"}]},
        "NDX": {"data": []},
        "RUT": {"data": []},
        "SPY": {"data": [{"symbol": "SPY261116C00500000", "instrument_id": "spy-1"}]},
        "QQQ": {"data": [{"symbol": "QQQ261116C00500000", "instrument_id": "qqq-1"}]},
        "IWM": {"data": [{"symbol": "IWM261116C00250000", "instrument_id": "iwm-1"}]},
    }

    class _Probe:
        def list_contracts(self, params: dict) -> dict:
            if params.get("root_symbol") == "SPXW":
                return pages["SPXW"]
            symbol = params["underlying_symbols"]
            if symbol == "RUT":
                raise EntitlementError("HTTP 403", http_status=403)
            return pages[symbol]

        def option_snapshots(self, symbols: list[str]) -> dict:
            raise AssertionError(symbols)

        def underlying_snapshot(self, symbol: str) -> dict:
            raise AssertionError(symbol)

    report = probe_capabilities(
        _Probe(),
        now=_Clock().now,
        sleep=_Clock().sleep,
        buckets=limiters_for("sandbox"),
    )
    assert report.covered == ("SPX", "SPXW", "SPY", "QQQ", "IWM")
    assert "NDX" in report.missing
    assert "RUT" in report.missing
    by_name = {row.name: row for row in report.rows}
    assert by_name["NDX"].contracts_returned == 0
    assert by_name["NDX"].covered is False
    assert by_name["RUT"].queried is True
    assert "403" in by_name["RUT"].note


def test_dry_run_does_nothing_without_keys_and_refuses_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("WEBULL_APP_KEY", raising=False)
    monkeypatch.delenv("WEBULL_APP_SECRET", raising=False)
    monkeypatch.setenv("WEBULL_ENVIRONMENT", "sandbox")

    def _blocked(name, *args, **kwargs):
        if name == "webull" or name.startswith("webull."):
            raise AssertionError(name)
        return original(name, *args, **kwargs)

    import builtins

    original = builtins.__import__
    monkeypatch.setattr(builtins, "__import__", _blocked)
    assert main([]) == 0
    monkeypatch.setenv("WEBULL_APP_KEY", "not-a-real-key")
    monkeypatch.setenv("WEBULL_APP_SECRET", "not-a-real-secret")
    monkeypatch.setenv("WEBULL_ENVIRONMENT", "production")
    assert main(["SPY"]) == 2


def test_token_bucket_rejects_a_zero_capacity() -> None:
    with pytest.raises(ValueError):
        TokenBucket(0)
