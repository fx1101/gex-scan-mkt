# SPDX-License-Identifier: Apache-2.0
"""The Pine overlay and the exporter share one level string."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from scripts.export_tv import main

from gex_scanner.adapters.fixtures import load_chain_file
from gex_scanner.scanner import Universe, scan_universe
from gex_scanner.tv.level_export import format_level_string, parse_level_string, write_export

ROOT = Path(__file__).resolve().parents[1]
PINE = ROOT / "src" / "gex_scanner" / "tv" / "pine" / "gex_levels.pine"
README = (ROOT / "README.md").read_text(encoding="utf-8")


def test_pine_source_parses_the_exporter_example() -> None:
    source = PINE.read_text(encoding="utf-8")
    example = "SPX|flip:6700|call:6800|put:6600|dte_call:6750|dte_put:"
    assert example in source
    assert 'str.split(level_string, "|")' in source
    assert 'str.split(part, ":")' in source
    parsed = parse_level_string(example)
    assert parsed["symbol"] == "SPX"
    assert parsed["flip"] == 6700.0
    assert parsed["dte_put"] is None
    again = format_level_string(
        "SPX",
        flip=6700.0,
        call_wall=6800.0,
        put_wall=6600.0,
        dte_call_wall=6750.0,
        dte_put_wall=None,
    )
    assert parse_level_string(again)["call"] == 6800.0
    assert "Pine Editor" in README
    assert "scripts/export_tv.py" in README


def test_export_script_prints_a_string_and_writes_json(tmp_path: Path, capsys) -> None:
    destination = tmp_path / "levels.json"
    status = main(
        [
            str(ROOT / "tests" / "fixtures" / "spx_chain.json"),
            "--json",
            str(destination),
        ]
    )
    printed = capsys.readouterr().out.strip()
    assert status == 0
    parsed = parse_level_string(printed)
    assert parsed["symbol"] == "SPX"
    document = destination.read_text(encoding="utf-8")
    assert '"places_orders": false' in document
    snapshot = load_chain_file(ROOT / "tests" / "fixtures" / "spy_chain.json")
    result = scan_universe(
        {"SPY": snapshot},
        Universe(indexes=("SPY",), etfs=(), stocks=()),
        as_of=datetime(2026, 11, 16, 15, 0, tzinfo=UTC),
        active_session="us_rth",
    )
    path = write_export(result.rows[0], tmp_path / "spy.json")
    assert path.is_file()
