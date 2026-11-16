# SPDX-License-Identifier: Apache-2.0
"""Parse a recorded Cboe chain, or download one when ``--network`` is set.

The default path does not open a socket.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from gex_scanner.adapters.cboe_delayed import fetch_delayed_quotes, parse_cboe_payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("symbol", nargs="?", help="Underlying, such as NOK or SPX")
    parser.add_argument(
        "--network",
        action="store_true",
        help="Download the delayed chain. Omit this to refuse a live fetch.",
    )
    parser.add_argument(
        "--fixture",
        type=Path,
        help="Parse this saved payload instead of downloading.",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=Path("data/cache"),
        help="Gzip directory used only with --network.",
    )
    args = parser.parse_args(argv)
    if args.fixture is not None:
        snapshot = parse_cboe_payload(args.fixture.read_text(encoding="utf-8"))
    elif not args.symbol:
        parser.error("pass a symbol or --fixture")
    elif not args.network:
        print(
            "Live Cboe fetch is off. Re-run with --network to download a delayed chain.",
            file=sys.stderr,
        )
        return 2
    else:
        snapshot = fetch_delayed_quotes(args.symbol, network=True, cache_dir=args.cache_dir)
    print(
        f"{snapshot.underlying} spot={snapshot.spot} field={snapshot.spot_field} "
        f"contracts={len(snapshot.contracts)} session={snapshot.session_key} "
        f"snapshot={snapshot.snapshot_id}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
