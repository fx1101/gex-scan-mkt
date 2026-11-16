# SPDX-License-Identifier: Apache-2.0
"""Alert evaluation and JSON webhooks. This module does not place orders."""

from __future__ import annotations

import json
import logging
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from gex_scanner.redact import log_event
from gex_scanner.scanner.ranker import SIGN_DUST, UNVALIDATED

logger = logging.getLogger(__name__)

# Names that must not appear in an outbound or inbound payload.
FORBIDDEN_FIELDS = frozenset(
    {
        "api_key",
        "app_key",
        "app_secret",
        "token",
        "webhook_url",
        "authorization",
        "order",
        "orders",
        "qty",
        "quantity",
        "side",
        "place_order",
    }
)

# A price within this percent of a wall counts as a test of that wall.
WALL_TEST_PCT = 0.1


@dataclass(frozen=True)
class LevelState:
    underlying: str
    price: float
    flip: float | None
    call_wall: float | None
    put_wall: float | None
    net_gex: float
    session_key: str
    session_ct: str
    session_et: str
    captured_at: datetime


@dataclass(frozen=True)
class Alert:
    kind: str
    underlying: str
    session_key: str
    session_ct: str
    session_et: str
    message: str
    fields: dict[str, Any]


def _sign(net_gex: float) -> int:
    if abs(net_gex) <= SIGN_DUST:
        return 0
    return 1 if net_gex > 0 else -1


def _side(price: float, level: float | None) -> int | None:
    if level is None:
        return None
    if price > level:
        return 1
    if price < level:
        return -1
    return 0


def _near(price: float, level: float | None) -> bool:
    if level is None or price == 0:
        return False
    return abs(price - level) / abs(price) * 100.0 <= WALL_TEST_PCT


def reject_order_fields(payload: Any) -> None:
    """Refuse order, secret, and webhook fields anywhere in a JSON tree."""

    if isinstance(payload, dict):
        for key, value in payload.items():
            if str(key).lower() in FORBIDDEN_FIELDS:
                raise ValueError(f"payload field {key} is not allowed")
            reject_order_fields(value)
    elif isinstance(payload, list):
        for item in payload:
            reject_order_fields(item)


def evaluate_alerts(
    previous: LevelState | None,
    current: LevelState,
    *,
    now: datetime,
    stale_seconds: float,
) -> list[Alert]:
    """Compare two states. The first observation can open a session, not a trade."""

    if now.tzinfo is None or current.captured_at.tzinfo is None:
        raise ValueError("timestamps must be timezone-aware")
    found: list[Alert] = []

    def _alert(kind: str, message: str, **fields: Any) -> None:
        found.append(
            Alert(
                kind=kind,
                underlying=current.underlying,
                session_key=current.session_key,
                session_ct=current.session_ct,
                session_et=current.session_et,
                message=message,
                fields=fields,
            )
        )

    if previous is None or previous.session_key != current.session_key:
        _alert("session_open", f"{current.session_key} briefing")
    if previous is not None:
        before = _side(previous.price, current.flip)
        after = _side(current.price, current.flip)
        if before not in (None, 0) and after not in (None, 0) and before != after:
            _alert(
                "flip_crossed",
                "price crossed the primary flip",
                flip=current.flip,
                previous_price=previous.price,
                price=current.price,
            )
        for name, level in (("call_wall", current.call_wall), ("put_wall", current.put_wall)):
            if _near(current.price, level) and not _near(previous.price, level):
                _alert(
                    "wall_tested",
                    f"price tested {name}",
                    wall=name,
                    level=level,
                    price=current.price,
                )
        if _sign(previous.net_gex) != _sign(current.net_gex):
            _alert(
                "regime_sign_change",
                "net GEX sign changed",
                previous_net_gex=previous.net_gex,
                net_gex=current.net_gex,
            )
    age = (now - current.captured_at).total_seconds()
    if age > stale_seconds:
        _alert("data_stale", "chain is older than the staleness window", age_seconds=age)
    return found


def alert_payload(alert: Alert) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "event": alert.kind,
        "underlying": alert.underlying,
        "session_key": alert.session_key,
        "session_ct": alert.session_ct,
        "session_et": alert.session_et,
        "message": alert.message,
        "badge": UNVALIDATED,
        "places_orders": False,
    }
    payload.update(alert.fields)
    reject_order_fields(payload)
    if payload["places_orders"] is not False:
        raise ValueError("alerts must not place orders")
    return payload


def post_json(url: str, payload: dict[str, Any], timeout: float = 5.0) -> int:
    """POST one JSON object. The URL is not copied into the body."""

    reject_order_fields(payload)
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return int(response.status)


def dispatch(
    alerts: list[Alert],
    *,
    webhook_url: str = "",
    post: Callable[[str, dict[str, Any]], int] = post_json,
) -> list[dict[str, Any]]:
    """Log every alert and POST it when a webhook URL is set."""

    sent: list[dict[str, Any]] = []
    for alert in alerts:
        payload = alert_payload(alert)
        log_event(logger, "alert", kind=alert.kind, underlying=alert.underlying)
        if webhook_url:
            post(webhook_url, payload)
        sent.append(payload)
    return sent


def ingest_tradingview(body: Any) -> dict[str, Any]:
    """Accept a TradingView webhook body. Order fields are rejected."""

    if not isinstance(body, dict):
        raise ValueError("TradingView body must be an object")
    reject_order_fields(body)
    for key in ("symbol", "price", "event"):
        if key not in body:
            raise ValueError(f"TradingView body is missing {key}")
    return {
        "event": str(body["event"]),
        "underlying": str(body["symbol"]),
        "price": float(body["price"]),
        "level": None if body.get("level") is None else str(body["level"]),
        "places_orders": False,
        "badge": UNVALIDATED,
    }
