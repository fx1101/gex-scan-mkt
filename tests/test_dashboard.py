# SPDX-License-Identifier: Apache-2.0
"""Dashboard HTML shows the ranked table, bars, and the unvalidated badge."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from gex_scanner.dashboard.render import render_index, render_symbol
from gex_scanner.scanner import load_fixture_chains, load_universe, scan_universe
from gex_scanner.store import SnapshotStore

ROOT = Path(__file__).resolve().parents[1]


def _scan():
    universe = load_universe(ROOT / "config" / "universe.toml")
    chains = load_fixture_chains(ROOT / "tests" / "fixtures", universe.symbols())
    result = scan_universe(
        chains,
        universe,
        as_of=datetime(2026, 11, 16, 15, 0, tzinfo=UTC),
        active_session="us_rth",
    )
    return result


def test_dashboard_renders_ranked_setups_and_a_strike_profile() -> None:
    result = _scan()
    page = render_index(list(result.rows))
    assert "Ranked setups" in page
    assert "unvalidated hypothesis" in page
    assert "SPX" in page
    assert "SPY" in page
    assert ">Refresh<" in page
    banned = " ".join(("best", "most", "profitable"))
    assert banned not in page.lower()
    symbol = render_symbol(result.rows[0])
    assert "GEX by strike" in symbol
    assert "Expiry breakdown" in symbol
    assert 'class="bar' in symbol
    assert "unvalidated hypothesis" in symbol


def test_symbol_page_marks_levels_and_switches_expiry_chips() -> None:
    result = _scan()
    spy = next(row for row in result.rows if row.underlying == "SPY")
    page = render_symbol(spy)
    assert f"Vendor {spy.vendor}" in page
    assert spy.captured_at_utc in page
    assert f"Session {spy.snapshot_session_key}" in page
    assert f"Data age {spy.data_age_seconds:.0f} seconds" in page
    assert ">Refresh<" in page
    assert "scan_fixtures.py" in page
    assert "alpaca_snapshot.py" in page
    assert "webull_snapshot.py" in page
    assert "does not place an order" in page
    assert "unvalidated hypothesis" in page
    for name in ("all", "0dte", "lte_7d", "lte_30d"):
        assert f"expiry={name}" in page
    assert "Call wall" in page
    assert "Put wall" in page
    assert ">Flip " in page or ">Flip<" in page
    assert "Spot " in page
    assert "Repriced net GEX" in page
    assert "<polyline" in page
    assert "claude" not in page.lower()
    zero = render_symbol(spy, expiry="0dte")
    assert "Filter 0dte" in zero
    assert 'class="chip on"' in zero
    assert zero.count("<rect") < page.count("<rect")


def test_refresh_reads_the_latest_stored_row_and_old_rows_still_load(tmp_path: Path) -> None:
    result = _scan()
    path = tmp_path / "scanner.sqlite"
    store = SnapshotStore(path)
    store.save_scan(result.rows)
    store.close()
    again = SnapshotStore(path)
    latest = again.latest("SPY")
    assert latest is not None
    assert len(latest.views) == 4
    assert latest.views[0].curve
    page = render_index(again.latest_rows())
    assert latest.captured_at_utc in page
    connection = sqlite3.connect(path)
    raw_id, raw_json = connection.execute(
        "SELECT snapshot_id, row_json FROM snapshots WHERE underlying = 'SPY'"
    ).fetchone()
    payload = json.loads(raw_json)
    del payload["views"]
    connection.execute(
        "UPDATE snapshots SET row_json = ? WHERE snapshot_id = ?",
        (json.dumps(payload), raw_id),
    )
    connection.commit()
    connection.close()
    reread = SnapshotStore(path)
    old = reread.latest("SPY")
    assert old is not None
    assert old.views == ()
    assert "No repriced curve is stored with this snapshot." in render_symbol(old)
    again.close()
    reread.close()
