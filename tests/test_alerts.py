# SPDX-License-Identifier: Apache-2.0
"""Alert rules, and a loopback webhook that records the JSON body."""

from __future__ import annotations

import json
import threading
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from gex_scanner.alerts.webhooks import (
    LevelState,
    dispatch,
    evaluate_alerts,
    ingest_tradingview,
    post_json,
)

NOW = datetime(2026, 11, 16, 15, 0, tzinfo=UTC)
EARLIER = datetime(2026, 11, 16, 14, 0, tzinfo=UTC)


def _state(**overrides) -> LevelState:
    fields = {
        "underlying": "SPX",
        "price": 6000.0,
        "flip": 5990.0,
        "call_wall": 6100.0,
        "put_wall": 5900.0,
        "net_gex": 1000.0,
        "session_key": "us_rth",
        "session_ct": "2026-11-16T09:00:00-06:00",
        "session_et": "2026-11-16T10:00:00-05:00",
        "captured_at": EARLIER,
    }
    fields.update(overrides)
    return LevelState(**fields)


def test_flip_wall_regime_session_and_stale_alerts() -> None:
    previous = _state(price=5980.0, net_gex=1000.0, session_key="us_gth_index")
    current = _state(price=6000.0, net_gex=-1000.0, call_wall=6000.0)
    alerts = evaluate_alerts(previous, current, now=NOW, stale_seconds=60)
    kinds = [item.kind for item in alerts]
    assert "session_open" in kinds
    assert "flip_crossed" in kinds
    assert "wall_tested" in kinds
    assert "regime_sign_change" in kinds
    assert "data_stale" in kinds
    opening = evaluate_alerts(None, _state(), now=EARLIER, stale_seconds=3600)
    assert [item.kind for item in opening] == ["session_open"]


def test_ingest_rejects_an_order_field() -> None:
    event = ingest_tradingview({"symbol": "SPX", "price": 6001, "event": "price_crossed"})
    assert event["places_orders"] is False
    with pytest.raises(ValueError, match="order"):
        ingest_tradingview({"symbol": "SPX", "price": 1, "event": "x", "order": {"qty": 1}})


class _Recorder(BaseHTTPRequestHandler):
    received: list[dict] = []

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length).decode("utf-8"))
        self.received.append(payload)
        self.send_response(204)
        self.end_headers()

    def log_message(self, fmt: str, *args) -> None:
        return


@pytest.mark.network
def test_alerts_post_to_a_local_dummy_server() -> None:
    _Recorder.received = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Recorder)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        alerts = evaluate_alerts(
            _state(price=5980.0),
            _state(price=6005.0),
            now=EARLIER,
            stale_seconds=3600,
        )
        url = f"http://{host}:{port}/hook"
        sent = dispatch(alerts, webhook_url=url, post=post_json)
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()
    assert sent
    assert _Recorder.received
    body = _Recorder.received[0]
    assert body["places_orders"] is False
    assert body["event"] == "flip_crossed"
    assert "order" not in body
    assert url not in json.dumps(body)
