# SPDX-License-Identifier: Apache-2.0
"""Dry-run one Alpaca option chain. Does not place orders.

With ``ALPACA_API_KEY`` or ``ALPACA_API_SECRET`` empty, the script prints a
line and exits. It does not open a socket.

When both are set, the download uses the market-data host inside
``gex_scanner.adapters.alpaca``. This file does not name auth headers, does
not call a trading host, and does not construct an order client.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

from gex_scanner.adapters.alpaca import (
    CoverageError,
    EntitlementError,
    RateLimitError,
    download_chain,
)
from gex_scanner.adapters.fixtures import write_raw_cache


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("symbol", nargs="?", help="One US equity or ETF, such as SPY")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/cache"),
        help="Directory for the gzipped raw payload. Used only after a download.",
    )
    args = parser.parse_args(argv)
    key = os.environ.get("ALPACA_API_KEY", "")
    secret = os.environ.get("ALPACA_API_SECRET", "")
    if not key or not secret:
        print("Alpaca keys are not set. Nothing was downloaded.")
        return 0
    if not args.symbol:
        print("Pass one symbol to download.", file=sys.stderr)
        return 2
    try:
        snapshot = download_chain(args.symbol, key=key, secret=secret, as_of=datetime.now(UTC))
    except CoverageError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    path = write_raw_cache(snapshot, args.output)
    print(
        f"{snapshot.underlying} contracts={len(snapshot.contracts)} "
        f"session={snapshot.session_key} wrote={path}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except CoverageError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2) from exc
    except (EntitlementError, RateLimitError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc
