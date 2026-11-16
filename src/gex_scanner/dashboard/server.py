# SPDX-License-Identifier: Apache-2.0
"""Local read-only dashboard plus an incoming TradingView webhook."""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlparse

from gex_scanner.alerts.webhooks import ingest_tradingview
from gex_scanner.dashboard.render import render_index, render_symbol
from gex_scanner.store.sqlite import SnapshotStore


class DashboardHandler(BaseHTTPRequestHandler):
    store: SnapshotStore

    def log_message(self, fmt: str, *args) -> None:
        return

    def _send(self, status: int, body: str) -> None:
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/":
            self._send(200, render_index(self.store.latest_rows()))
            return
        prefix = "/symbol/"
        if path.startswith(prefix):
            symbol = unquote(path[len(prefix) :]).upper()
            row = self.store.latest(symbol)
            if row is None:
                self._send(404, "not found")
                return
            self._send(200, render_symbol(row))
            return
        self._send(404, "not found")

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path != "/hooks/tradingview":
            self._send(404, "not found")
            return
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        try:
            event = ingest_tradingview(json.loads(raw.decode("utf-8")))
        except (ValueError, json.JSONDecodeError) as exc:
            self._send(400, str(exc))
            return
        self.store.save_alert(event)
        self._send(204, "")


def serve(store: SnapshotStore, host: str = "127.0.0.1", port: int = 8765) -> None:
    DashboardHandler.store = store
    server = ThreadingHTTPServer((host, port), DashboardHandler)
    server.serve_forever()
