# SPDX-License-Identifier: Apache-2.0
"""Alpaca market-data option chains. Parsing does not open a socket.

Written against Alpaca's public Market Data docs as read on 2026-11-22
(option chain and option snapshots). No file from simonro/Edge-GEX-Lab
was copied.

Live calls belong in ``scripts/alpaca_snapshot.py`` and only run when
``ALPACA_API_KEY`` and ``ALPACA_API_SECRET`` are both set. Those values
become the headers ``APCA-API-KEY-ID`` and ``APCA-API-SECRET-KEY`` here.
Every request stays on ``https://data.alpaca.markets``. This module does
not call a trading host, does not open a websocket, and does not place orders.

The chain route is ``GET /v1beta1/options/snapshots/{underlying}``. Spot for
an equity or ETF is ``GET /v2/stocks/{symbol}/trades/latest``. The published
snapshot object has ``latestQuote``, ``latestTrade``, ``impliedVolatility``,
and ``greeks``. Open interest is not in that schema. It is copied only when
a payload includes ``open_interest``. A missing ``greeks`` object stays null
and is flagged. This module does not compute Black-Scholes gamma.
"""

from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any, Protocol
from zoneinfo import ZoneInfo

from gex_scanner.redact import log_event
from gex_scanner.sessions.calendar import session_at
from gex_scanner.types import ChainSnapshot, Contract

logger = logging.getLogger(__name__)

DATA_HOST = "https://data.alpaca.markets"
_CT = ZoneInfo("America/Chicago")
_OCC = re.compile(r"^([A-Z]{1,6})(\d{2})(\d{2})(\d{2})([CP])(\d{8})$")
_UNDERLYING = re.compile(r"^[A-Z]{1,6}$")
_PAGE_CAP = 20
_PAGE_LIMIT = 1000
# About Market Data, Trading API Basic cell, as cited by the 2026-11-22 survey.
# The snapshot OpenAPI example uses 100 as a sample header, not this budget.
_BASIC_PER_MINUTE = 200
_GREEK_NAMES = ("delta", "gamma", "theta", "vega", "rho")

# Index names and futures roots this adapter does not claim.
_NOT_CLAIMED = frozenset(
    {"NDX", "RUT", "SPX", "SPXW", "XSP", "VIX", "ES", "NQ", "RTY", "MES", "MNQ", "M2K"}
)

_HEADER_KEY = "APCA-API-KEY-ID"
_HEADER_SECRET = "APCA-API-SECRET-KEY"


class CoverageError(ValueError):
    """The underlying is outside the equity and ETF scope of this adapter."""


class EntitlementError(RuntimeError):
    """The account is not allowed to read this market-data call."""

    def __init__(self, message: str, *, http_status: int | None = None) -> None:
        super().__init__(message)
        self.http_status = http_status


class RateLimitError(RuntimeError):
    """HTTP 429. ``retry_after`` is seconds, when the response gave one."""

    def __init__(self, message: str, *, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


@dataclass(frozen=True)
class AlpacaConfig:
    """Chain window. Not the GEX sign convention."""

    moneyness_band: float = 0.15
    dte_cap: int = 30
    page_limit: int = _PAGE_LIMIT
    max_retries: int = 3
    stock_feed: str = "iex"

    def __post_init__(self) -> None:
        if not 0.0 < self.moneyness_band < 1.0:
            raise ValueError("moneyness_band must be between 0 and 1")
        if self.dte_cap < 0:
            raise ValueError("dte_cap must be >= 0")
        if not 1 <= self.page_limit <= _PAGE_LIMIT:
            raise ValueError(f"page_limit must be 1..{_PAGE_LIMIT}")
        if self.max_retries < 0:
            raise ValueError("max_retries must be >= 0")
        if self.stock_feed not in {"iex", "sip"}:
            raise ValueError("stock_feed must be iex or sip")


@dataclass
class TokenBucket:
    """One budget. Time is injected so tests do not sleep."""

    capacity: int = _BASIC_PER_MINUTE
    window_seconds: float = 60.0

    def __post_init__(self) -> None:
        if self.capacity < 1:
            raise ValueError("capacity must be positive")
        self.tokens = float(self.capacity)
        self.refill_per_second = self.capacity / self.window_seconds
        self.updated_at: float | None = None

    def acquire(self, now: Callable[[], float], sleep: Callable[[float], None]) -> None:
        while True:
            clock = now()
            if self.updated_at is None:
                self.updated_at = clock
            elapsed = clock - self.updated_at
            self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_per_second)
            self.updated_at = clock
            if self.tokens >= 1.0:
                self.tokens -= 1.0
                return
            sleep((1.0 - self.tokens) / self.refill_per_second)


class AlpacaTransport(Protocol):
    """Recorded or live market-data responses. No order method."""

    def latest_trade(self, symbol: str, feed: str) -> Any:
        """Latest stock trade for spot."""

    def option_chain(self, underlying: str, params: Mapping[str, Any]) -> Any:
        """One option-chain snapshot page."""


@dataclass(frozen=True)
class ChainPage:
    snapshots: dict[str, dict[str, Any]]
    next_page_token: str | None


@dataclass(frozen=True)
class FetchCounts:
    returned: int
    kept: int
    skipped: int
    pages: int
    skip_reasons: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class AlpacaFetch:
    snapshot: ChainSnapshot
    counts: FetchCounts


def auth_headers(key: str, secret: str) -> dict[str, str]:
    """Map this repo's env names onto Alpaca's header names. Does not log them."""

    if not key or not secret:
        raise ValueError("Alpaca keys are empty")
    return {_HEADER_KEY: key, _HEADER_SECRET: secret}


def require_equity_or_etf(underlying: str) -> str:
    """Reject index and futures names. This adapter does not claim them."""

    symbol = underlying.strip().upper()
    if symbol.startswith("/") or symbol in _NOT_CLAIMED or not _UNDERLYING.fullmatch(symbol):
        raise CoverageError(
            f"Alpaca adapter does not claim {underlying!r}. "
            "Scope is US equity and ETF underlyings. "
            "NDX, RUT, SPX, and futures are not requested."
        )
    return symbol


def chain_url(underlying: str, params: Mapping[str, Any]) -> str:
    """Data-host chain URL. Trading hosts and order paths are rejected."""

    symbol = require_equity_or_etf(underlying)
    pairs = {key: value for key, value in params.items() if value is not None}
    return _data_url(f"/v1beta1/options/snapshots/{symbol}", urllib.parse.urlencode(pairs))


def trade_url(symbol: str, feed: str) -> str:
    """Data-host latest-trade URL."""

    clean = require_equity_or_etf(symbol)
    if feed not in {"iex", "sip"}:
        raise ValueError("stock feed must be iex or sip")
    query = urllib.parse.urlencode({"feed": feed})
    return _data_url(f"/v2/stocks/{clean}/trades/latest", query)


def _data_url(path: str, query: str) -> str:
    if path.startswith("/v2/orders") or "orders" in path:
        raise ValueError("order paths are not used")
    url = f"{DATA_HOST}{path}"
    if query:
        url = f"{url}?{query}"
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or parsed.netloc != "data.alpaca.markets":
        raise ValueError(f"refusing host {parsed.netloc}")
    return url


def classify_status(
    http_status: int,
    *,
    retry_after: float | None = None,
) -> None:
    """Raise for statuses that must not become an empty chain."""

    if http_status == 429:
        raise RateLimitError("Alpaca HTTP 429 on a market-data call", retry_after=retry_after)
    if http_status in {401, 403}:
        raise EntitlementError(
            f"Alpaca refused the market-data call (HTTP {http_status}).",
            http_status=http_status,
        )
    if http_status >= 400:
        raise RuntimeError(f"Alpaca HTTP {http_status}")


def call_with_backoff(
    fn: Callable[[], Any],
    bucket: TokenBucket,
    *,
    now: Callable[[], float],
    sleep: Callable[[float], None],
    max_retries: int,
) -> Any:
    """Acquire a token, call ``fn``, and retry only on ``RateLimitError``."""

    delay = 1.0
    for attempt in range(max_retries + 1):
        bucket.acquire(now, sleep)
        try:
            return fn()
        except RateLimitError as exc:
            if attempt == max_retries:
                raise
            sleep(delay if exc.retry_after is None else exc.retry_after)
            delay *= 2
    raise RuntimeError("backoff loop exited without a result")


def _number(value: Any, field: str) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ValueError(f"Alpaca field {field} must be a number")
    try:
        return float(value)
    except ValueError as exc:
        raise ValueError(f"Alpaca field {field} must be a number") from exc


def _timestamp(value: str) -> datetime:
    text = value.strip().replace("Z", "+00:00")
    matched = re.match(r"^(.*\.)(\d+)(.*)$", text)
    if matched:
        text = matched.group(1) + matched.group(2)[:6] + matched.group(3)
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def underlying_price(payload: Any) -> float:
    """Read the latest-trade price. IEX is one venue, not the consolidated print."""

    if not isinstance(payload, dict):
        raise ValueError("Alpaca trade payload must be an object")
    trade = payload.get("trade")
    if not isinstance(trade, dict):
        raise ValueError("Alpaca trade payload is missing trade")
    price = _number(trade.get("p"), "p")
    if price is None or price <= 0:
        raise ValueError("Alpaca latest trade is missing a positive price")
    return price


def parse_chain_page(payload: Any) -> ChainPage:
    if not isinstance(payload, dict) or not isinstance(payload.get("snapshots"), dict):
        raise ValueError("Alpaca chain page must contain a snapshots object")
    snapshots = {
        str(symbol): row for symbol, row in payload["snapshots"].items() if isinstance(row, dict)
    }
    if len(snapshots) != len(payload["snapshots"]):
        raise ValueError("Alpaca chain page contains a non-object snapshot")
    token = payload.get("next_page_token")
    if token is not None:
        token = str(token)
    return ChainPage(snapshots=snapshots, next_page_token=token)


def _from_occ(symbol: str) -> tuple[str, date, str, float]:
    match = _OCC.fullmatch(symbol)
    if match is None:
        raise ValueError(f"Alpaca option symbol is not OCC form: {symbol!r}")
    root, year, month, day, right, strike = match.groups()
    return (
        root,
        date(2000 + int(year), int(month), int(day)),
        "call" if right == "C" else "put",
        int(strike) / 1000.0,
    )


def _contract_meta(rows: list[Mapping[str, Any]] | None) -> dict[str, Mapping[str, Any]]:
    meta: dict[str, Mapping[str, Any]] = {}
    for row in rows or []:
        symbol = str(row.get("symbol") or "")
        if symbol:
            meta[symbol] = row
    return meta


def _merged_meta(snapshot: Mapping[str, Any], extra: Mapping[str, Any]) -> dict[str, Any]:
    """Snapshot keys win. The published snapshot schema has none of these."""

    merged = dict(extra)
    for key in ("open_interest", "open_interest_date", "size", "multiplier", "style"):
        if key in snapshot:
            merged[key] = snapshot[key]
    return merged


def map_contract(
    symbol: str,
    raw: Mapping[str, Any],
    *,
    as_of: datetime,
    feed: str,
    extra: Mapping[str, Any] | None = None,
) -> Contract:
    """Map one snapshot object. Missing greeks stay null."""

    root, expiry, right, strike = _from_occ(symbol)
    meta = _merged_meta(raw, extra or {})
    flags: list[str] = [f"feed_{feed}", "settlement_not_in_payload"]
    greeks = raw.get("greeks")
    values: dict[str, float | None] = {}
    if not isinstance(greeks, dict):
        flags.append("missing_greeks")
        values = {name: None for name in _GREEK_NAMES}
    else:
        missing = False
        for name in _GREEK_NAMES:
            if name not in greeks or greeks.get(name) is None:
                values[name] = None
                missing = True
            else:
                values[name] = _number(greeks.get(name), name)
        if missing or values["gamma"] is None:
            flags.append("missing_greeks")
    iv = _number(raw.get("impliedVolatility"), "impliedVolatility")
    if iv is None:
        flags.append("missing_iv")
    if "open_interest" not in meta or meta.get("open_interest") is None:
        if "open_interest" in meta and meta.get("open_interest") is None:
            flags.append("open_interest_null")
        else:
            flags.append("open_interest_not_in_snapshot")
        open_interest = None
    else:
        open_interest = _number(meta.get("open_interest"), "open_interest")
    oi_date = meta.get("open_interest_date")
    if oi_date:
        flags.append(f"open_interest_date={str(oi_date)[:10]}")
    size = meta.get("size", meta.get("multiplier"))
    non_standard = False
    reason = None
    if size is None:
        multiplier = 100.0
        flags.append("multiplier_not_in_payload")
    else:
        multiplier = _number(size, "size") or 0.0
        if multiplier != 100.0:
            non_standard = True
            reason = "multiplier"
            flags.append("non_standard_multiplier")
    style_raw = str(meta.get("style") or "").lower()
    if style_raw in {"american", "european"}:
        style = style_raw
    else:
        style = "unknown"
        flags.append("style_not_in_payload")
    quote = raw.get("latestQuote") if isinstance(raw.get("latestQuote"), dict) else {}
    trade = raw.get("latestTrade") if isinstance(raw.get("latestTrade"), dict) else {}
    quote_time = None
    if quote.get("t"):
        quote_time = _timestamp(str(quote["t"]))
    volume = _number(trade.get("s"), "s")
    if volume is not None:
        flags.append("volume_is_last_trade_size")
    as_of_ct = as_of.astimezone(_CT)
    return Contract(
        occ_symbol=symbol,
        root=root,
        expiry=expiry,
        dte=(expiry - as_of_ct.date()).days,
        right=right,
        strike=strike,
        multiplier=multiplier,
        exercise_style=style,
        settlement=None,
        bid=_number(quote.get("bp"), "bp"),
        ask=_number(quote.get("ap"), "ap"),
        last=_number(trade.get("p"), "p"),
        volume=volume,
        open_interest=open_interest,
        iv=iv,
        delta=values["delta"],
        gamma=values["gamma"],
        theta=values["theta"],
        vega=values["vega"],
        rho=values["rho"],
        quote_time=quote_time,
        non_standard=non_standard,
        non_standard_reason=reason,
        flow_sign=None,
        provider_flags=tuple(flags),
    )


def _in_band(strike: float, spot: float, band: float) -> bool:
    return spot * (1.0 - band) <= strike <= spot * (1.0 + band)


def chain_params(
    *,
    feed: str,
    spot: float,
    as_of: datetime,
    config: AlpacaConfig,
    page_token: str | None,
) -> dict[str, Any]:
    """Query the project's moneyness band and DTE cap. Feed is explicit."""

    if feed not in {"indicative", "opra"}:
        raise ValueError("option feed must be indicative or opra")
    session_day = as_of.astimezone(_CT).date()
    params: dict[str, Any] = {
        "feed": feed,
        "limit": config.page_limit,
        "strike_price_gte": spot * (1.0 - config.moneyness_band),
        "strike_price_lte": spot * (1.0 + config.moneyness_band),
        "expiration_date_gte": session_day.isoformat(),
        "expiration_date_lte": (session_day + timedelta(days=config.dte_cap)).isoformat(),
    }
    if page_token:
        params["page_token"] = page_token
    return params


def build_chain(
    *,
    underlying: str,
    spot: float,
    spot_field: str,
    as_of: datetime,
    feed: str,
    snapshots: Mapping[str, Mapping[str, Any]],
    contract_rows: list[Mapping[str, Any]] | None,
    raw_json: str,
) -> tuple[ChainSnapshot, FetchCounts]:
    if as_of.tzinfo is None:
        raise ValueError("as_of must be timezone-aware")
    meta = _contract_meta(contract_rows)
    contracts = tuple(
        map_contract(symbol, row, as_of=as_of, feed=feed, extra=meta.get(symbol))
        for symbol, row in snapshots.items()
    )
    label = session_at(as_of, underlying)
    stamp = as_of.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    snapshot = ChainSnapshot(
        vendor=f"alpaca-{feed}",
        snapshot_id=f"alpaca-{feed}-{underlying}-{stamp}",
        captured_at_utc=as_of.astimezone(UTC),
        captured_at_ct=label.ct,
        underlying=underlying,
        spot=spot,
        spot_field=spot_field,
        contracts=contracts,
        futures=(),
        raw_json=raw_json,
        session_key=label.key,
        session_ct=label.ct,
        session_et=label.et,
    )
    counts = FetchCounts(
        returned=len(snapshots),
        kept=len(contracts),
        skipped=0,
        pages=0,
        skip_reasons=(),
    )
    return snapshot, counts


def fetch_chain(
    transport: AlpacaTransport,
    underlying: str,
    *,
    as_of: datetime,
    config: AlpacaConfig | None = None,
    feed: str = "indicative",
    contract_rows: list[Mapping[str, Any]] | None = None,
    now: Callable[[], float] | None = None,
    sleep: Callable[[float], None] | None = None,
    bucket: TokenBucket | None = None,
) -> AlpacaFetch:
    """Read spot and one equity or ETF chain. No trading-host call."""

    symbol = require_equity_or_etf(underlying)
    if feed not in {"indicative", "opra"}:
        raise ValueError("option feed must be indicative or opra")
    if config is None:
        config = AlpacaConfig()
    clock = now or _wall_now
    pause = sleep or _wall_sleep
    limiter = bucket or TokenBucket()
    trade_payload = call_with_backoff(
        lambda: transport.latest_trade(symbol, config.stock_feed),
        limiter,
        now=clock,
        sleep=pause,
        max_retries=config.max_retries,
    )
    spot = underlying_price(trade_payload)
    pages: list[Any] = []
    snapshots: dict[str, dict[str, Any]] = {}
    token: str | None = None
    seen: set[str] = set()
    for _page in range(_PAGE_CAP):
        params = chain_params(
            feed=feed,
            spot=spot,
            as_of=as_of,
            config=config,
            page_token=token,
        )
        body = call_with_backoff(
            lambda params=params: transport.option_chain(symbol, params),
            limiter,
            now=clock,
            sleep=pause,
            max_retries=config.max_retries,
        )
        pages.append(body)
        page = parse_chain_page(body)
        snapshots.update(page.snapshots)
        nxt = page.next_page_token
        if not nxt or nxt in seen:
            break
        seen.add(nxt)
        token = nxt
    else:
        raise RuntimeError("Alpaca option chain exceeded the page cap")

    meta = _contract_meta(contract_rows)
    kept: dict[str, dict[str, Any]] = {}
    skipped: list[tuple[str, str]] = []
    for occ, row in snapshots.items():
        _root, expiry, _right, strike = _from_occ(occ)
        dte = (expiry - as_of.astimezone(_CT).date()).days
        if dte > config.dte_cap:
            skipped.append((occ, "dte_cap"))
        elif not _in_band(strike, spot, config.moneyness_band):
            skipped.append((occ, "moneyness"))
        else:
            kept[occ] = row
    raw = json.dumps(
        {
            "underlying_trade": trade_payload,
            "pages": pages,
            "contracts": list(contract_rows or []),
        }
    )
    snapshot, _unused = build_chain(
        underlying=symbol,
        spot=spot,
        spot_field=config.stock_feed,
        as_of=as_of,
        feed=feed,
        snapshots=kept,
        contract_rows=list(meta[symbol_key] for symbol_key in kept if symbol_key in meta),
        raw_json=raw,
    )
    counts = FetchCounts(
        returned=len(snapshots),
        kept=len(kept),
        skipped=len(skipped),
        pages=len(pages),
        skip_reasons=tuple(skipped),
    )
    log_event(
        logger,
        "alpaca_chain",
        underlying=symbol,
        feed=feed,
        returned=counts.returned,
        kept=counts.kept,
        skipped=counts.skipped,
        pages=counts.pages,
    )
    return AlpacaFetch(snapshot=snapshot, counts=counts)


class AlpacaProvider:
    """``ChainProvider`` over an injected transport. Tests pass a recorded book."""

    vendor = "alpaca"

    def __init__(
        self,
        transport: AlpacaTransport,
        *,
        as_of: datetime,
        config: AlpacaConfig | None = None,
        feed: str = "indicative",
        contract_rows: list[Mapping[str, Any]] | None = None,
        now: Callable[[], float] | None = None,
        sleep: Callable[[float], None] | None = None,
        bucket: TokenBucket | None = None,
    ) -> None:
        self._transport = transport
        self._as_of = as_of
        self._config = config
        self._feed = feed
        self._contract_rows = contract_rows
        self._now = now
        self._sleep = sleep
        self._bucket = bucket

    def get_chain(self, underlying: str, snapshot_id: str | None = None) -> ChainSnapshot:
        fetched = fetch_chain(
            self._transport,
            underlying,
            as_of=self._as_of,
            config=self._config,
            feed=self._feed,
            contract_rows=self._contract_rows,
            now=self._now,
            sleep=self._sleep,
            bucket=self._bucket,
        )
        snapshot = fetched.snapshot
        if snapshot_id is None:
            return snapshot
        return ChainSnapshot(
            vendor=snapshot.vendor,
            snapshot_id=snapshot_id,
            captured_at_utc=snapshot.captured_at_utc,
            captured_at_ct=snapshot.captured_at_ct,
            underlying=snapshot.underlying,
            spot=snapshot.spot,
            spot_field=snapshot.spot_field,
            contracts=snapshot.contracts,
            futures=snapshot.futures,
            raw_json=snapshot.raw_json,
            session_key=snapshot.session_key,
            session_ct=snapshot.session_ct,
            session_et=snapshot.session_et,
        )


class UrllibTransport:
    """HTTPS client for ``data.alpaca.markets`` only. Constructed by the dry run."""

    def __init__(self, headers: Mapping[str, str]) -> None:
        self._headers = dict(headers)

    def latest_trade(self, symbol: str, feed: str) -> Any:
        return self._get(trade_url(symbol, feed))

    def option_chain(self, underlying: str, params: Mapping[str, Any]) -> Any:
        return self._get(chain_url(underlying, params))

    def _get(self, url: str) -> Any:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme != "https" or parsed.netloc != "data.alpaca.markets":
            raise RuntimeError(f"refusing host {parsed.netloc}")
        if "orders" in parsed.path:
            raise RuntimeError("order paths are not used")
        request = urllib.request.Request(url, headers=self._headers, method="GET")
        try:
            with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
                status = getattr(response, "status", 200)
                classify_status(status)
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            retry_after = None
            raw_retry = exc.headers.get("Retry-After") if exc.headers else None
            if raw_retry is not None:
                retry_after = float(raw_retry)
            classify_status(exc.code, retry_after=retry_after)
            raise


def download_chain(
    symbol: str,
    *,
    key: str,
    secret: str,
    as_of: datetime,
    feed: str = "indicative",
) -> ChainSnapshot:
    """One underlying from the data host. Refuses uncovered names before the request."""

    require_equity_or_etf(symbol)
    transport = UrllibTransport(auth_headers(key, secret))
    return fetch_chain(transport, symbol, as_of=as_of, feed=feed).snapshot


def _wall_now() -> float:
    return datetime.now(UTC).timestamp()


def _wall_sleep(seconds: float) -> None:
    import time

    time.sleep(seconds)
