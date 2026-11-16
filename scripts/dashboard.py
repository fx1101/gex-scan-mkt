# SPDX-License-Identifier: Apache-2.0
"""Serve the local dashboard from a SQLite file. Binds to loopback."""

from __future__ import annotations

import argparse
from pathlib import Path

from gex_scanner.dashboard import serve
from gex_scanner.store import SnapshotStore


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=Path("data/scanner.sqlite"))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args(argv)
    if args.host not in {"127.0.0.1", "localhost"}:
        raise SystemExit("The dashboard binds to loopback only.")
    serve(SnapshotStore(args.db), host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
