# SPDX-License-Identifier: Apache-2.0
"""Dry-run one Webull option chain. Does not place orders.

With ``WEBULL_APP_KEY`` or ``WEBULL_APP_SECRET`` empty, the script prints a
line and exits. It does not import the SDK and it does not open a socket.

When both are set, ``WEBULL_ENVIRONMENT`` must be ``sandbox``. Production is
refused. The download then uses the official package
``webull-openapi-python-sdk`` (import name ``webull``) and its US region
table. This file does not embed an API host and does not call any order
method.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from gex_scanner.adapters.fixtures import write_raw_cache
from gex_scanner.adapters.webull import (
    EntitlementError,
    RateLimitError,
    WebullConfig,
    classify_status,
    fetch_chain,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("symbol", nargs="?", help="One underlying, such as SPY")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/cache"),
        help="Directory for the gzipped raw payload. Used only after a download.",
    )
    args = parser.parse_args(argv)
    key = os.environ.get("WEBULL_APP_KEY", "")
    secret = os.environ.get("WEBULL_APP_SECRET", "")
    environment = os.environ.get("WEBULL_ENVIRONMENT", "sandbox") or "sandbox"
    if not key or not secret:
        print("Webull keys are not set. Nothing was downloaded.")
        return 0
    if environment.lower() != "sandbox":
        print(
            f"Refusing WEBULL_ENVIRONMENT={environment!r}. This dry run uses sandbox only.",
            file=sys.stderr,
        )
        return 2
    if not args.symbol:
        print("Pass one symbol to download.", file=sys.stderr)
        return 2
    snapshot = _download(args.symbol)
    path = write_raw_cache(snapshot, args.output)
    print(
        f"{snapshot.underlying} contracts={len(snapshot.contracts)} "
        f"session={snapshot.session_key} wrote={path}"
    )
    return 0


class _SdkTransport:
    """Sandbox data client. No trade client is constructed."""

    def __init__(self, data_client: Any) -> None:
        self._data = data_client

    def underlying_snapshot(self, symbol: str) -> Any:
        response = self._data.market_data.get_snapshot(symbol, "US_STOCK")
        return _body(response)

    def list_contracts(self, params: dict[str, Any]) -> Any:
        response = self._data.instrument.list_option_contracts(**params)
        return _body(response)

    def option_snapshots(self, symbols: list[str]) -> Any:
        response = self._data.option_market_data.get_option_snapshot(symbols, "US_OPTION")
        return _body(response)


def _body(response: Any) -> Any:
    status = getattr(response, "status_code", None)
    if isinstance(status, int):
        retry_after = None
        headers = getattr(response, "headers", None) or {}
        raw_retry = headers.get("Retry-After") if hasattr(headers, "get") else None
        if raw_retry is not None:
            retry_after = float(raw_retry)
        classify_status(status, retry_after=retry_after)
    if hasattr(response, "json"):
        return response.json()
    return response


def _download(symbol: str) -> Any:
    try:
        from webull.core.client import ApiClient
        from webull.data.data_client import DataClient
    except ImportError as exc:
        raise SystemExit(
            "webull-openapi-python-sdk is not installed. Nothing was downloaded."
        ) from exc
    client = ApiClient(os.environ["WEBULL_APP_KEY"], os.environ["WEBULL_APP_SECRET"], "us")
    result = fetch_chain(
        _SdkTransport(DataClient(client)),
        symbol,
        as_of=datetime.now(UTC),
        config=WebullConfig(environment="sandbox"),
    )
    return result.snapshot


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (EntitlementError, RateLimitError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc
