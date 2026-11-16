# SPDX-License-Identifier: Apache-2.0
"""Rank the fixture universe and store the rows. No network."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

from gex_scanner.scanner import load_fixture_chains, load_universe, scan_universe
from gex_scanner.store import SnapshotStore


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--universe", type=Path, default=Path("config/universe.toml"))
    parser.add_argument("--fixtures", type=Path, default=Path("tests/fixtures"))
    parser.add_argument("--db", type=Path, default=Path("data/scanner.sqlite"))
    parser.add_argument("--session", default="us_rth")
    parser.add_argument("--as-of", default="2026-11-16T15:00:00+00:00")
    args = parser.parse_args(argv)
    universe = load_universe(args.universe)
    chains = load_fixture_chains(args.fixtures, universe.symbols())
    as_of = datetime.fromisoformat(args.as_of)
    if as_of.tzinfo is None:
        as_of = as_of.replace(tzinfo=UTC)
    result = scan_universe(chains, universe, as_of=as_of, active_session=args.session)
    store = SnapshotStore(args.db)
    store.save_scan(result.rows, chains)
    store.close()
    for row in result.rows:
        print(
            f"{row.underlying} score={row.score:.6f} "
            f"regime={row.regime_sign} session={row.snapshot_session_key}"
        )
    if result.skipped:
        print("skipped " + ",".join(result.skipped))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
