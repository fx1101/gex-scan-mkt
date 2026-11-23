# SPDX-License-Identifier: Apache-2.0
"""Alpaca mapping from a recorded field example. No sockets."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from scripts.alpaca_snapshot import main

from gex_scanner.adapters.alpaca import (
    AlpacaProvider,
    CoverageError,
    RateLimitError,
    TokenBucket,
    auth_headers,
    chain_url,
    classify_status,
    download_chain,
    fetch_chain,
    trade_url,
)
from gex_scanner.config import EngineConfig
from gex_scanner.engine.quality import assess_contract

FIXTURE = Path(__file__).parent / "fixtures" / "recorded" / "alpaca_spy_chain.json"
AS_OF = datetime(2026, 11, 16, 15, 0, tzinfo=UTC)
ROOT = Path(__file__).resolve().parents[1]


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
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.trade_calls: list[tuple[str, str]] = []
        self.chain_calls: list[dict] = []
        self.fail_times = 0

    def latest_trade(self, symbol: str, feed: str) -> dict:
        self.trade_calls.append((symbol, feed))
        return self.payload["underlying_trade"]

    def option_chain(self, underlying: str, params: dict) -> dict:
        assert underlying == "SPY"
        if self.fail_times:
            self.fail_times -= 1
            raise RateLimitError("HTTP 429", retry_after=0.5)
        self.chain_calls.append(dict(params))
        if params.get("page_token") == "page-2":
            return self.payload["pages"][1]
        return self.payload["pages"][0]


def test_recorded_chain_maps_quotes_oi_and_leaves_missing_gamma_null() -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    book = _Book(payload)
    clock = _Clock()
    provider = AlpacaProvider(
        book,
        as_of=AS_OF,
        contract_rows=payload["contracts"],
        now=clock.now,
        sleep=clock.sleep,
        bucket=TokenBucket(),
    )
    snapshot = provider.get_chain("SPY")
    by_symbol = {item.occ_symbol: item for item in snapshot.contracts}

    assert snapshot.vendor == "alpaca-indicative"
    assert snapshot.spot == 500.0
    assert snapshot.spot_field == "iex"
    assert snapshot.futures == ()
    assert snapshot.session_key == "us_rth"
    assert set(by_symbol) == {"SPY261116C00500000", "SPY261116P00490000"}
    call = by_symbol["SPY261116C00500000"]
    assert call.right == "call"
    assert call.strike == 500.0
    assert call.gamma == 0.02
    assert call.iv == 0.2
    assert call.open_interest == 10.0
    assert call.multiplier == 100.0
    assert call.exercise_style == "american"
    assert call.bid == 1.2
    assert call.ask == 1.3
    assert call.last == 1.25
    assert call.volume == 3.0
    assert call.dte == 0
    assert call.flow_sign is None
    assert "open_interest_date=2026-11-13" in call.provider_flags
    assert "feed_indicative" in call.provider_flags
    assert "missing_greeks" not in call.provider_flags
    put = by_symbol["SPY261116P00490000"]
    assert put.iv == 0.4
    assert put.gamma is None
    assert put.delta is None
    assert put.open_interest is None
    assert "missing_greeks" in put.provider_flags
    assert "open_interest_not_in_snapshot" in put.provider_flags
    assert "multiplier_not_in_payload" in put.provider_flags
    quality = assess_contract(put, EngineConfig(), captured_at_utc=snapshot.captured_at_utc)
    assert quality.include is False
    assert "missing_gamma" in quality.exclusion_reasons
    assert book.trade_calls == [("SPY", "iex")]
    assert book.chain_calls[0]["feed"] == "indicative"
    assert book.chain_calls[0]["strike_price_gte"] == pytest.approx(425.0)
    assert book.chain_calls[0]["strike_price_lte"] == pytest.approx(575.0)
    assert book.chain_calls[1]["page_token"] == "page-2"
    reasons = {}
    result = fetch_chain(
        book,
        "SPY",
        as_of=AS_OF,
        contract_rows=payload["contracts"],
        now=clock.now,
        sleep=clock.sleep,
        bucket=TokenBucket(),
    )
    reasons = dict(result.counts.skip_reasons)
    assert reasons["SPY261218C00500000"] == "dte_cap"
    assert reasons["SPY261116C00200000"] == "moneyness"


def test_ndx_and_futures_are_not_requested() -> None:
    book = _Book(json.loads(FIXTURE.read_text(encoding="utf-8")))
    provider = AlpacaProvider(book, as_of=AS_OF, now=_Clock().now, sleep=_Clock().sleep)
    with pytest.raises(CoverageError, match="NDX"):
        provider.get_chain("NDX")
    with pytest.raises(CoverageError, match="futures"):
        provider.get_chain("/ES")
    with pytest.raises(CoverageError):
        provider.get_chain("SPX")
    assert book.trade_calls == []
    assert book.chain_calls == []


def test_urls_stay_on_the_data_host_and_headers_are_mapped_here() -> None:
    url = chain_url(
        "SPY",
        {"feed": "indicative", "limit": 1000, "strike_price_gte": 425},
    )
    assert url.startswith("https://data.alpaca.markets/v1beta1/options/snapshots/SPY?")
    assert "paper-api.alpaca.markets" not in url
    assert "api.alpaca.markets" not in url
    assert "/v2/orders" not in url
    trade = trade_url("QQQ", "iex")
    assert trade == "https://data.alpaca.markets/v2/stocks/QQQ/trades/latest?feed=iex"
    headers = auth_headers("example-key", "example-secret")
    assert headers["APCA-API-KEY-ID"] == "example-key"
    assert headers["APCA-API-SECRET-KEY"] == "example-secret"
    script = (ROOT / "scripts" / "alpaca_snapshot.py").read_text(encoding="utf-8")
    assert "APCA-API-KEY-ID" not in script
    assert "APCA-API-SECRET-KEY" not in script
    with pytest.raises(RateLimitError):
        classify_status(429, retry_after=1.0)


def test_http_429_backs_off_without_leaving_the_recorded_book() -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    book = _Book(payload)
    book.fail_times = 1
    clock = _Clock()
    result = fetch_chain(
        book,
        "spy",
        as_of=AS_OF,
        contract_rows=payload["contracts"],
        now=clock.now,
        sleep=clock.sleep,
        bucket=TokenBucket(),
    )
    assert result.counts.kept == 2
    assert 0.5 in clock.slept
    assert result.snapshot.underlying == "SPY"


def test_dry_run_does_nothing_without_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ALPACA_API_KEY", raising=False)
    monkeypatch.delenv("ALPACA_API_SECRET", raising=False)

    def _blocked(*_args, **_kwargs):
        raise AssertionError("download")

    monkeypatch.setattr("scripts.alpaca_snapshot.download_chain", _blocked)
    assert main([]) == 0
    monkeypatch.setenv("ALPACA_API_KEY", "example-key")
    assert main(["SPY"]) == 0
    monkeypatch.setattr("scripts.alpaca_snapshot.download_chain", download_chain)
    monkeypatch.setenv("ALPACA_API_SECRET", "example-secret")
    assert main(["NDX"]) == 2


def test_basic_bucket_waits_after_two_hundred_calls() -> None:
    bucket = TokenBucket()
    clock = _Clock()
    for _ in range(200):
        bucket.acquire(clock.now, clock.sleep)
    assert clock.slept == []
    bucket.acquire(clock.now, clock.sleep)
    assert clock.slept == [pytest.approx(60.0 / 200)]
