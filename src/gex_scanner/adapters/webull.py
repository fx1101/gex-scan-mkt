# SPDX-License-Identifier: Apache-2.0
"""Webull OpenAPI option chains. Parsing and limiting do not open sockets.

Live calls belong in ``scripts/webull_snapshot.py`` and only run when sandbox
keys are set. This module does not place orders.

Paths and field names follow the official SDK
``webull-openapi-python-sdk`` (Apache-2.0) as read on 2026-11-16:

- ``GET /trading/instruments/options/contracts/list`` via
  ``list_option_contracts`` (category ``US_OPTION``, ``pagination_key``,
  ``underlying_symbols``, ``root_symbol``, strike bounds).
- ``GET /market-data/options/snapshots/list``, at most 20 symbols.
  Mapped fields: ``open_interest``, ``imp_vol``, ``gamma``, ``delta``,
  ``theta``, ``vega``, ``rho``, ``bid``, ``ask``, ``volume``,
  ``strike_price``.
- Underlying spot is the stock snapshot ``price`` field.

Rate limits are the 2026-11-15 research-note figures: sandbox 30/60s for
both endpoints; production snapshots 300/60s and contract list 60/60s.
HTTP 401 and 403 are entitlement failures. HTTP 429 backs off.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any, Protocol
from zoneinfo import ZoneInfo

from gex_scanner.redact import log_event
from gex_scanner.sessions.calendar import session_at
from gex_scanner.types import ChainSnapshot, Contract

logger = logging.getLogger(__name__)

_ET = ZoneInfo("America/New_York")
_OCC = re.compile(r"^([A-Z]{1,6})(\d{2})(\d{2})(\d{2})([CP])(\d{8})$")
_SNAPSHOT_BATCH = 20
_PAGE_CAP = 50

# Requests per 60 seconds. Sandbox contract-list limit is the figure already
# recorded in docs/DATA_SOURCES.md from the 2026-11-15 note.
_LIMITS = {
    "sandbox": {"snapshots": 30, "contracts": 30},
    "production": {"snapshots": 300, "contracts": 60},
}

# Probe names from the Phase 4 acceptance list. SPXW is a root on SPX.
PROBE_QUERIES: tuple[tuple[str, dict[str, str]], ...] = (
    ("SPX", {"underlying_symbols": "SPX"}),
    ("SPXW", {"underlying_symbols": "SPX", "root_symbol": "SPXW"}),
    ("NDX", {"underlying_symbols": "NDX"}),
    ("RUT", {"underlying_symbols": "RUT"}),
    ("SPY", {"underlying_symbols": "SPY"}),
    ("QQQ", {"underlying_symbols": "QQQ"}),
    ("IWM", {"underlying_symbols": "IWM"}),
)

_ENTITLEMENT = (
    "Webull refused the call (HTTP {status}). This is an entitlement or "
    "permission failure, not a missing contract. OpenAPI options data needs "
    "the OPRA Real-Time Non-display subscription. The app or desktop quote "
    "login does not cover it. Sandbox stays delayed unless that subscription "
    "is also on."
)


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
class WebullConfig:
    """Quota filter and limiter settings. Not the GEX sign convention."""

    environment: str = "sandbox"
    moneyness_band: float = 0.15
    dte_cap: int = 30
    snapshot_batch_size: int = _SNAPSHOT_BATCH
    max_retries: int = 3

    def __post_init__(self) -> None:
        if self.environment not in _LIMITS:
            raise ValueError("environment must be sandbox or production")
        if not 0.0 < self.moneyness_band < 1.0:
            raise ValueError("moneyness_band must be between 0 and 1")
        if self.dte_cap < 0:
            raise ValueError("dte_cap must be >= 0")
        if not 1 <= self.snapshot_batch_size <= _SNAPSHOT_BATCH:
            raise ValueError(f"snapshot_batch_size must be 1..{_SNAPSHOT_BATCH}")
        if self.max_retries < 0:
            raise ValueError("max_retries must be >= 0")


@dataclass
class TokenBucket:
    """One endpoint's budget. Time is injected so tests do not sleep."""

    capacity: int
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


@dataclass(frozen=True)
class Limiters:
    contracts: TokenBucket
    snapshots: TokenBucket


def limiters_for(environment: str) -> Limiters:
    rates = _LIMITS[environment]
    return Limiters(
        contracts=TokenBucket(rates["contracts"]),
        snapshots=TokenBucket(rates["snapshots"]),
    )


def classify_status(
    http_status: int,
    *,
    error_msg: str = "",
    retry_after: float | None = None,
) -> None:
    """Raise for statuses the adapter must not treat as an empty chain."""

    if http_status == 429:
        raise RateLimitError("Webull HTTP 429 on a market-data call", retry_after=retry_after)
    if http_status in {401, 403}:
        raise EntitlementError(_ENTITLEMENT.format(status=http_status), http_status=http_status)
    lowered = error_msg.lower()
    if any(word in lowered for word in ("permission", "entitlement", "subscription")):
        raise EntitlementError(_ENTITLEMENT.format(status=http_status), http_status=http_status)
    if http_status >= 400:
        raise RuntimeError(f"Webull HTTP {http_status}: {error_msg}".rstrip())


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


class WebullTransport(Protocol):
    """Recorded or live responses. Implementations must not place orders."""

    def list_contracts(self, params: Mapping[str, Any]) -> Any:
        """One contract-list page."""

    def option_snapshots(self, symbols: list[str]) -> Any:
        """Snapshots for at most 20 OCC symbols."""

    def underlying_snapshot(self, symbol: str) -> Any:
        """Stock snapshot whose ``price`` is the chain spot."""


@dataclass(frozen=True)
class ListedContract:
    occ_symbol: str
    root: str
    underlying: str
    expiry: date
    dte: int
    right: str
    strike: float
    multiplier: float
    exercise_style: str
    settlement: str | None
    non_standard: bool
    non_standard_reason: str | None
    provider_flags: tuple[str, ...]
    status: str | None


@dataclass(frozen=True)
class ContractPage:
    contracts: tuple[dict[str, Any], ...]
    pagination_key: str | None


@dataclass(frozen=True)
class FetchCounts:
    listed: int
    quoted: int
    skipped: int
    batches: int
    skip_reasons: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class CapabilityRow:
    """One probe. ``covered`` is true only when the page returned a contract."""

    name: str
    queried: bool
    contracts_returned: int
    covered: bool
    note: str


@dataclass(frozen=True)
class CapabilityReport:
    rows: tuple[CapabilityRow, ...]

    @property
    def covered(self) -> tuple[str, ...]:
        return tuple(row.name for row in self.rows if row.covered)

    @property
    def missing(self) -> tuple[str, ...]:
        return tuple(row.name for row in self.rows if not row.covered)


@dataclass(frozen=True)
class WebullFetch:
    snapshot: ChainSnapshot
    counts: FetchCounts


def _items(payload: Any) -> tuple[list[Any], str | None]:
    if isinstance(payload, list):
        return payload, None
    if not isinstance(payload, dict):
        raise ValueError("Webull payload must be an object or a list")
    page_key = payload.get("pagination_key")
    if page_key is None:
        page_key = payload.get("next_pagination_key")
    if page_key is not None:
        page_key = str(page_key)
    for name in ("data", "items", "result"):
        if name in payload and isinstance(payload[name], list):
            return payload[name], page_key
    return [], page_key


def parse_contract_page(payload: Any) -> ContractPage:
    rows, page_key = _items(payload)
    contracts = tuple(row for row in rows if isinstance(row, dict))
    if len(contracts) != len(rows):
        raise ValueError("Webull contract list contains a non-object")
    return ContractPage(contracts=contracts, pagination_key=page_key)


def parse_snapshot_rows(payload: Any) -> tuple[dict[str, Any], ...]:
    rows, _page_key = _items(payload)
    parsed = tuple(row for row in rows if isinstance(row, dict))
    if len(parsed) != len(rows):
        raise ValueError("Webull snapshot list contains a non-object")
    return parsed


def underlying_price(payload: Any) -> float:
    """Read ``price`` from a stock snapshot object or a one-row list."""

    rows, _page_key = _items(payload)
    if not rows and isinstance(payload, dict) and "price" in payload:
        rows = [payload]
    if len(rows) != 1 or not isinstance(rows[0], dict):
        raise ValueError("Webull underlying snapshot must contain one object")
    price = _number(rows[0].get("price"), "price")
    if price is None or price <= 0:
        raise ValueError("Webull underlying snapshot is missing a positive price")
    return price


def _number(value: Any, field: str) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ValueError(f"Webull field {field} must be a number")
    try:
        return float(value)
    except ValueError as exc:
        raise ValueError(f"Webull field {field} must be a number") from exc


def _expiry(raw: Mapping[str, Any]) -> date | None:
    for key in ("init_exp_date", "expiration_date"):
        value = raw.get(key)
        if value:
            return date.fromisoformat(str(value)[:10])
    return None


def _from_occ(symbol: str) -> tuple[str, date, str, float] | None:
    match = _OCC.fullmatch(symbol)
    if match is None:
        return None
    root, year, month, day, right, strike = match.groups()
    return (
        root,
        date(2000 + int(year), int(month), int(day)),
        "call" if right == "C" else "put",
        int(strike) / 1000.0,
    )


def map_listed_contract(raw: Mapping[str, Any], as_of: datetime) -> ListedContract:
    """Map one contracts/list object. A missing multiplier is not replaced."""

    symbol = str(raw.get("symbol") or "")
    if not symbol:
        raise ValueError("Webull contract is missing symbol")
    occ = _from_occ(symbol)
    expiry = _expiry(raw)
    option_type = str(raw.get("option_type") or "").upper()
    right = {"CALL": "call", "PUT": "put"}.get(option_type)
    strike = _number(raw.get("strike_price"), "strike_price")
    root = str(raw.get("root_symbol") or "")
    if occ is not None:
        occ_root, occ_expiry, occ_right, occ_strike = occ
        root = root or occ_root
        expiry = expiry or occ_expiry
        right = right or occ_right
        strike = strike if strike is not None else occ_strike
    if expiry is None or right is None or strike is None or not root:
        raise ValueError(f"Webull contract {symbol} is missing expiry, right, strike, or root")
    style_raw = str(raw.get("style") or "").upper()
    flags: list[str] = []
    if style_raw in {"AMERICAN", "EUROPEAN"}:
        style = style_raw.lower()
    else:
        style = "unknown"
        flags.append("style_not_in_payload")
    multiplier = _number(raw.get("multiplier"), "multiplier")
    non_standard = False
    reason = None
    deliverables = raw.get("deliverables")
    if isinstance(deliverables, list) and deliverables:
        non_standard = True
        reason = "deliverable"
        flags.append("non_standard_deliverable")
    if multiplier is None:
        multiplier = 0.0
        flags.append("multiplier_not_in_payload")
    elif multiplier != 100.0:
        non_standard = True
        reason = reason or "multiplier"
        flags.append("non_standard_multiplier")
    as_of_et = as_of.astimezone(_ET)
    underlying = str(raw.get("underlying_symbol") or root)
    return ListedContract(
        occ_symbol=symbol,
        root=root,
        underlying=underlying,
        expiry=expiry,
        dte=(expiry - as_of_et.date()).days,
        right=right,
        strike=strike,
        multiplier=multiplier,
        exercise_style=style,
        settlement=None if raw.get("settlement_method") is None else str(raw["settlement_method"]),
        non_standard=non_standard,
        non_standard_reason=reason,
        provider_flags=tuple(flags),
        status=None if raw.get("status") is None else str(raw.get("status")),
    )


def _in_band(strike: float, spot: float, band: float) -> bool:
    return spot * (1.0 - band) <= strike <= spot * (1.0 + band)


def select_contracts(
    listed: list[ListedContract],
    *,
    spot: float,
    config: WebullConfig,
) -> tuple[list[ListedContract], list[tuple[str, str]]]:
    """Apply the moneyness band and DTE cap before any snapshot call."""

    kept: list[ListedContract] = []
    skipped: list[tuple[str, str]] = []
    for contract in listed:
        if contract.status == "DELISTING":
            skipped.append((contract.occ_symbol, "delisting"))
        elif contract.dte > config.dte_cap:
            skipped.append((contract.occ_symbol, "dte_cap"))
        elif not _in_band(contract.strike, spot, config.moneyness_band):
            skipped.append((contract.occ_symbol, "moneyness"))
        else:
            kept.append(contract)
    return kept, skipped


def snapshot_batches(symbols: list[str], size: int) -> list[list[str]]:
    if size < 1 or size > _SNAPSHOT_BATCH:
        raise ValueError(f"batch size must be 1..{_SNAPSHOT_BATCH}")
    return [symbols[index : index + size] for index in range(0, len(symbols), size)]


def _contract_from_parts(listed: ListedContract, quote: Mapping[str, Any] | None) -> Contract:
    quote = quote or {}
    return Contract(
        occ_symbol=listed.occ_symbol,
        root=listed.root,
        expiry=listed.expiry,
        dte=listed.dte,
        right=listed.right,
        strike=listed.strike,
        multiplier=listed.multiplier,
        exercise_style=listed.exercise_style,
        settlement=listed.settlement,
        bid=_number(quote.get("bid"), "bid"),
        ask=_number(quote.get("ask"), "ask"),
        last=_number(quote.get("price"), "price"),
        volume=_number(quote.get("volume"), "volume"),
        open_interest=_number(quote.get("open_interest"), "open_interest"),
        iv=_number(quote.get("imp_vol"), "imp_vol"),
        delta=_number(quote.get("delta"), "delta"),
        gamma=_number(quote.get("gamma"), "gamma"),
        theta=_number(quote.get("theta"), "theta"),
        vega=_number(quote.get("vega"), "vega"),
        rho=_number(quote.get("rho"), "rho"),
        quote_time=None,
        non_standard=listed.non_standard,
        non_standard_reason=listed.non_standard_reason,
        provider_flags=listed.provider_flags,
    )


def build_chain(
    *,
    underlying: str,
    spot: float,
    as_of: datetime,
    listed: list[ListedContract],
    quotes: Mapping[str, Mapping[str, Any]],
    raw_json: str,
) -> ChainSnapshot:
    if as_of.tzinfo is None:
        raise ValueError("as_of must be timezone-aware")
    label = session_at(as_of, underlying)
    contracts = tuple(
        _contract_from_parts(item, quotes.get(item.occ_symbol))
        for item in listed
        if item.occ_symbol in quotes
    )
    stamp = as_of.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    return ChainSnapshot(
        vendor="webull",
        snapshot_id=f"webull-{underlying}-{stamp}",
        captured_at_utc=as_of.astimezone(UTC),
        captured_at_ct=label.ct,
        underlying=underlying,
        spot=spot,
        spot_field="price",
        contracts=contracts,
        raw_json=raw_json,
        session_key=label.key,
        session_ct=label.ct,
        session_et=label.et,
    )


def _list_params(underlying: str, spot: float, config: WebullConfig) -> dict[str, Any]:
    low = spot * (1.0 - config.moneyness_band)
    high = spot * (1.0 + config.moneyness_band)
    return {
        "category": "US_OPTION",
        "underlying_symbols": underlying,
        "status": "LISTING",
        "strike_price_gte": low,
        "strike_price_lte": high,
    }


def fetch_chain(
    transport: WebullTransport,
    underlying: str,
    *,
    as_of: datetime,
    config: WebullConfig | None = None,
    now: Callable[[], float] | None = None,
    sleep: Callable[[float], None] | None = None,
    buckets: Limiters | None = None,
) -> WebullFetch:
    """List, filter, and batch-snapshot one underlying.

    ``end_date`` is not sent. In the official SDK that parameter is an
    inclusive lower bound on expiration, not a DTE cap. The DTE cap is
    applied locally after the pages return.
    """

    if config is None:
        config = WebullConfig()
    clock = now or _wall_now
    pause = sleep or _wall_sleep
    limiter = buckets or limiters_for(config.environment)
    spot_payload = call_with_backoff(
        lambda: transport.underlying_snapshot(underlying),
        limiter.snapshots,
        now=clock,
        sleep=pause,
        max_retries=config.max_retries,
    )
    spot = underlying_price(spot_payload)
    params = _list_params(underlying, spot, config)
    pages: list[Any] = []
    listed: list[ListedContract] = []
    seen_keys: set[str] = set()
    page_key: str | None = None
    for _page in range(_PAGE_CAP):
        query = dict(params)
        if page_key:
            query["pagination_key"] = page_key
        body = call_with_backoff(
            lambda query=query: transport.list_contracts(query),
            limiter.contracts,
            now=clock,
            sleep=pause,
            max_retries=config.max_retries,
        )
        pages.append(body)
        page = parse_contract_page(body)
        listed.extend(map_listed_contract(row, as_of) for row in page.contracts)
        nxt = page.pagination_key
        if not nxt or nxt in seen_keys:
            break
        seen_keys.add(nxt)
        page_key = nxt
    else:
        raise RuntimeError("Webull contract list exceeded the page cap")

    kept, skipped = select_contracts(listed, spot=spot, config=config)
    batches = snapshot_batches([item.occ_symbol for item in kept], config.snapshot_batch_size)
    quote_rows: list[dict[str, Any]] = []
    for batch in batches:
        body = call_with_backoff(
            lambda batch=batch: transport.option_snapshots(batch),
            limiter.snapshots,
            now=clock,
            sleep=pause,
            max_retries=config.max_retries,
        )
        pages.append(body)
        quote_rows.extend(parse_snapshot_rows(body))
    quotes = {str(row.get("symbol")): row for row in quote_rows if row.get("symbol")}
    missing = [item.occ_symbol for item in kept if item.occ_symbol not in quotes]
    skipped.extend((symbol, "not_quoted") for symbol in missing)
    counts = FetchCounts(
        listed=len(listed),
        quoted=len(kept) - len(missing),
        skipped=len(skipped),
        batches=len(batches),
        skip_reasons=tuple(skipped),
    )
    by_symbol = {item.occ_symbol: item for item in kept}
    snapshot = build_chain(
        underlying=underlying,
        spot=spot,
        as_of=as_of,
        listed=[by_symbol[symbol] for symbol in quotes if symbol in by_symbol],
        quotes=quotes,
        raw_json=json.dumps(pages),
    )
    log_event(
        logger,
        "webull_chain",
        underlying=underlying,
        listed=counts.listed,
        quoted=counts.quoted,
        skipped=counts.skipped,
        batches=counts.batches,
    )
    return WebullFetch(snapshot=snapshot, counts=counts)


def probe_capabilities(
    transport: WebullTransport,
    *,
    config: WebullConfig | None = None,
    now: Callable[[], float] | None = None,
    sleep: Callable[[float], None] | None = None,
    buckets: Limiters | None = None,
) -> CapabilityReport:
    """Ask the contract list about each Phase 4 name. Empty is not coverage."""

    if config is None:
        config = WebullConfig()
    clock = now or _wall_now
    pause = sleep or _wall_sleep
    limiter = buckets or limiters_for(config.environment)
    rows: list[CapabilityRow] = []
    for name, extra in PROBE_QUERIES:
        params: dict[str, Any] = {"category": "US_OPTION", "status": "LISTING", **extra}
        try:
            body = call_with_backoff(
                lambda params=params: transport.list_contracts(params),
                limiter.contracts,
                now=clock,
                sleep=pause,
                max_retries=config.max_retries,
            )
        except EntitlementError as exc:
            rows.append(
                CapabilityRow(
                    name=name,
                    queried=True,
                    contracts_returned=0,
                    covered=False,
                    note=str(exc),
                )
            )
            continue
        page = parse_contract_page(body)
        count = sum(1 for row in page.contracts if row.get("symbol") or row.get("instrument_id"))
        rows.append(
            CapabilityRow(
                name=name,
                queried=True,
                contracts_returned=count,
                covered=count > 0,
                note="" if count else "contract list returned no contracts",
            )
        )
    return CapabilityReport(rows=tuple(rows))


def _wall_now() -> float:
    return datetime.now(UTC).timestamp()


def _wall_sleep(seconds: float) -> None:
    import time

    time.sleep(seconds)
