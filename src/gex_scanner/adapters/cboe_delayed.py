# SPDX-License-Identifier: Apache-2.0
"""Cboe delayed-quotes chain adapter.

Live HTTP is off unless ``network=True`` (the ``--network`` script flag).
Parsing a saved payload does not open a socket. The CDN needs no API key.

URL form, from the 2026-11-15 research note:
``https://cdn.cboe.com/api/global/delayed_quotes/options/{SYM}.json``
and ``.../options/_{SYM}.json`` for indexes. The CDN may 307 to
``cdn-api.cboe.com``. This client follows that redirect.

Field names below are the ones present on the payloads saved 2026-11-16.
The payload has no multiplier, exercise style, or settlement. Those are
flagged rather than treated as vendor facts. Option ``iv`` is stored as
the number in the file. Underlying ``iv30`` is not copied onto contracts.
"""

from __future__ import annotations

import json
import re
import urllib.request
from datetime import UTC, date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from gex_scanner.adapters.fixtures import write_raw_cache
from gex_scanner.sessions.calendar import session_at
from gex_scanner.sessions.keys import CBOE_INDEX_UNDERLYINGS
from gex_scanner.types import ChainSnapshot, Contract

_CDN = "https://cdn.cboe.com/api/global/delayed_quotes/options"
_INDEXES = frozenset(CBOE_INDEX_UNDERLYINGS)
_OCC = re.compile(r"^([A-Z]{1,6})(\d{2})(\d{2})(\d{2})([CP])(\d{8})$")
_ET = ZoneInfo("America/New_York")

_MULTIPLIER_FLAG = "multiplier_not_in_payload"
_STYLE_FLAG = "style_not_in_payload"


def canonical_underlying(symbol: str) -> str:
    """Strip the CDN's ``_`` or ``^`` prefix. ``_SPX`` and ``^SPX`` are SPX."""

    text = symbol.strip().upper()
    if text.startswith("^"):
        text = text[1:]
    if text.startswith("_"):
        text = text[1:]
    if not text:
        raise ValueError("Cboe symbol is empty")
    return text


def delayed_quote_url(symbol: str) -> str:
    """CDN URL for one underlying. Indexes use a leading underscore."""

    underlying = canonical_underlying(symbol)
    leaf = f"_{underlying}" if underlying in _INDEXES else underlying
    return f"{_CDN}/{leaf}.json"


def _naive_utc(value: str) -> datetime:
    """Parse a Cboe chain timestamp.

    On the 2026-11-16 NOK recording, ``timestamp`` matched the HTTP
    Last-Modified GMT clock within a few seconds. A naive timestamp is
    therefore read as UTC. An explicit offset is kept.
    """

    text = value.strip().replace(" ", "T")
    parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _naive_et(value: str) -> datetime:
    """Parse a contract ``last_trade_time``.

    The recorded payloads use a naive timestamp. NOK's underlying print
    ``2026-11-13T15:59:59`` and SPX's ``2026-11-13T16:14:59`` sit on the US
    cash close, so a naive contract time is read as America/New_York.
    """

    parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=_ET)
    return parsed


def _number(value: object, field: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"Cboe field {field} must be a number or null")
    return float(value)


def _contract(raw: dict[str, object], captured_et: datetime, security_type: str) -> Contract:
    symbol = str(raw.get("option") or "")
    match = _OCC.fullmatch(symbol)
    if match is None:
        raise ValueError(f"Cboe option symbol is not OCC form: {symbol!r}")
    root, year, month, day, right, strike_raw = match.groups()
    expiry = date(2000 + int(year), int(month), int(day))
    if security_type == "index":
        style, settlement = "european", "cash"
    elif security_type == "stock":
        style, settlement = "american", "physical"
    else:
        style, settlement = "unknown", None
    quote = raw.get("last_trade_time")
    quote_time = _naive_et(str(quote)) if isinstance(quote, str) and quote else None
    return Contract(
        occ_symbol=symbol,
        root=root,
        expiry=expiry,
        dte=(expiry - captured_et.date()).days,
        right="call" if right == "C" else "put",
        strike=int(strike_raw) / 1000.0,
        multiplier=100.0,
        exercise_style=style,
        settlement=settlement,
        bid=_number(raw.get("bid"), "bid"),
        ask=_number(raw.get("ask"), "ask"),
        last=_number(raw.get("last_trade_price"), "last_trade_price"),
        volume=_number(raw.get("volume"), "volume"),
        open_interest=_number(raw.get("open_interest"), "open_interest"),
        iv=_number(raw.get("iv"), "iv"),
        delta=_number(raw.get("delta"), "delta"),
        gamma=_number(raw.get("gamma"), "gamma"),
        theta=_number(raw.get("theta"), "theta"),
        vega=_number(raw.get("vega"), "vega"),
        rho=_number(raw.get("rho"), "rho"),
        quote_time=quote_time,
        provider_flags=(_MULTIPLIER_FLAG, _STYLE_FLAG),
    )


def parse_cboe_payload(raw_json: str) -> ChainSnapshot:
    """Parse one delayed-quotes JSON body. Does not touch the network."""

    payload = json.loads(raw_json)
    if not isinstance(payload, dict):
        raise ValueError("Cboe payload root must be an object")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise ValueError("Cboe payload is missing data")
    options = data.get("options")
    if not isinstance(options, list) or not options:
        raise ValueError("Cboe payload options must be a non-empty list")
    timestamp = payload.get("timestamp")
    if not isinstance(timestamp, str) or not timestamp.strip():
        raise ValueError("Cboe payload is missing timestamp")
    raw_symbol = data.get("symbol") or payload.get("symbol")
    if not isinstance(raw_symbol, str):
        raise ValueError("Cboe payload is missing symbol")
    underlying = canonical_underlying(raw_symbol)
    spot = _number(data.get("current_price"), "current_price")
    if spot is None:
        raise ValueError("Cboe payload is missing current_price")
    captured = _naive_utc(timestamp)
    captured_et = captured.astimezone(_ET)
    security_type = str(data.get("security_type") or "")
    contracts = tuple(
        _contract(item, captured_et, security_type) for item in options if isinstance(item, dict)
    )
    if len(contracts) != len(options):
        raise ValueError("Cboe options list contains a non-object")
    label = session_at(captured, underlying)
    stamp = captured.strftime("%Y%m%dT%H%M%SZ")
    return ChainSnapshot(
        vendor="cboe_delayed",
        snapshot_id=f"cboe-{underlying}-{stamp}",
        captured_at_utc=captured,
        captured_at_ct=label.ct,
        underlying=underlying,
        spot=spot,
        spot_field="current_price",
        contracts=contracts,
        raw_json=raw_json,
        session_key=label.key,
        session_ct=label.ct,
        session_et=label.et,
    )


def fetch_delayed_quotes(
    symbol: str,
    *,
    network: bool = False,
    cache_dir: Path | str | None = None,
    timeout: float = 30.0,
) -> ChainSnapshot:
    """GET one chain. Refuses unless ``network`` is true.

    A successful response is parsed and, when ``cache_dir`` is set, gzipped
    under vendor / symbol / snapshot_id.
    """

    if not network:
        raise RuntimeError(
            "Live Cboe fetch is off. Re-run with --network to download a delayed chain."
        )
    url = delayed_quote_url(symbol)
    request = urllib.request.Request(url, headers={"User-Agent": "gex-scanner"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read().decode("utf-8")
    snapshot = parse_cboe_payload(body)
    if cache_dir is not None:
        write_raw_cache(snapshot, cache_dir)
    return snapshot


class CboeDelayedProvider:
    """``ChainProvider`` for the delayed CDN or a recorded payload file."""

    vendor = "cboe_delayed"

    def __init__(
        self,
        *,
        network: bool = False,
        cache_dir: Path | str | None = None,
        fixture_path: Path | str | None = None,
    ) -> None:
        self.network = network
        self.cache_dir = cache_dir
        self.fixture_path = None if fixture_path is None else Path(fixture_path)

    def get_chain(self, underlying: str, snapshot_id: str | None = None) -> ChainSnapshot:
        if self.fixture_path is not None:
            snapshot = parse_cboe_payload(self.fixture_path.read_text(encoding="utf-8"))
        else:
            snapshot = fetch_delayed_quotes(
                underlying,
                network=self.network,
                cache_dir=self.cache_dir,
            )
        if snapshot.underlying != canonical_underlying(underlying):
            raise KeyError(f"{self.fixture_path or underlying} is {snapshot.underlying}")
        if snapshot_id is not None and snapshot.snapshot_id != snapshot_id:
            raise KeyError(f"snapshot_id is {snapshot.snapshot_id}, not {snapshot_id}")
        return snapshot
