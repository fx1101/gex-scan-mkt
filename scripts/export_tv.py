# SPDX-License-Identifier: Apache-2.0
"""Print a Pine level string and write the JSON artifact. No network."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

from gex_scanner.adapters.fixtures import load_chain_file
from gex_scanner.scanner import Universe, scan_universe
from gex_scanner.tv.level_export import format_row, write_export


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fixture", type=Path)
    parser.add_argument("--json", type=Path, default=None)
    parser.add_argument("--mapped", action="store_true")
    parser.add_argument("--as-of", default="2026-11-16T15:00:00+00:00")
    args = parser.parse_args(argv)
    snapshot = load_chain_file(args.fixture)
    as_of = datetime.fromisoformat(args.as_of)
    if as_of.tzinfo is None:
        as_of = as_of.replace(tzinfo=UTC)
    universe = Universe(indexes=(snapshot.underlying,), etfs=(), stocks=())
    result = scan_universe(
        {snapshot.underlying: snapshot},
        universe,
        as_of=as_of,
        active_session="us_rth",
    )
    row = result.rows[0]
    print(format_row(row, mapped=args.mapped))
    if args.json is not None:
        write_export(row, args.json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
