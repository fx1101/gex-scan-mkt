# SPDX-License-Identifier: Apache-2.0
"""Print GEX, walls, and quality flags for one fixture file. No network."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from gex_scanner.adapters.fixtures import load_chain_file
from gex_scanner.engine.gex import compute_symbol_gex


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fixture", type=Path, help="Path to a chain fixture JSON file")
    args = parser.parse_args(argv)
    snapshot = load_chain_file(args.fixture)
    result = compute_symbol_gex(snapshot)
    print(result.disclaimer)
    print(f"unit: {result.unit}")
    print(
        f"{result.underlying} spot={result.spot} field={result.spot_field} "
        f"snapshot={result.snapshot_id}"
    )
    print(f"net_gex: {result.net_gex:.4f}")
    print(f"call_gex: {result.call_gex:.4f}")
    print(f"put_gex: {result.put_gex:.4f}")
    _print_wall("call_wall", result.call_wall)
    _print_wall("put_wall", result.put_wall)
    _print_wall("gross_magnet", result.gross_magnet)
    print(
        "quality: "
        f"seen={result.quality.contracts_seen} "
        f"included={result.quality.contracts_included} "
        f"excluded={result.quality.contracts_excluded}"
    )
    for item in result.quality.excluded:
        reasons = ",".join(item.exclusion_reasons)
        print(f"excluded {item.occ_symbol}: {reasons}")
    return 0


def _print_wall(name: str, wall) -> None:
    if wall is None:
        print(f"{name}: none")
        return
    print(f"{name}: strike={wall.strike} gex={wall.gex:.4f} side={wall.spot_side}")


if __name__ == "__main__":
    sys.exit(main())
