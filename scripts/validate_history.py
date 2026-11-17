# SPDX-License-Identifier: Apache-2.0
"""Write the dated validation report from the history on disk. No network."""

from __future__ import annotations

from pathlib import Path

from gex_scanner.backtest.preregistered import write_report


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    report = write_report(root)
    history = report["history"]
    print(
        f"badge={report['badge']} chain_sessions={history['chain_sessions']} "
        f"passed={report['passed_count']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
