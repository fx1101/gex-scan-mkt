# SPDX-License-Identifier: Apache-2.0
"""SQLite replay keeps the ranked row and the basis."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from gex_scanner.scanner import load_fixture_chains, load_universe, scan_universe
from gex_scanner.sessions.basis import session_basis
from gex_scanner.store import SnapshotStore

ROOT = Path(__file__).resolve().parents[1]


def test_replay_returns_the_saved_row_and_basis(tmp_path: Path) -> None:
    universe = load_universe(ROOT / "config" / "universe.toml")
    chains = load_fixture_chains(ROOT / "tests" / "fixtures", ("SPX",))
    basis = session_basis("SPX", chains["SPX"].spot, chains["SPX"].spot + 12.5, "last_rth_close")
    result = scan_universe(
        chains,
        universe,
        as_of=datetime(2026, 11, 16, 15, 0, tzinfo=UTC),
        active_session="us_rth",
        bases={"SPX": basis},
    )
    path = tmp_path / "scanner.sqlite"
    store = SnapshotStore(path)
    store.save_scan(result.rows, chains)
    store.close()
    again = SnapshotStore(path)
    replayed = again.replay("SPX")
    stored_basis = again.basis_for(replayed[0].snapshot_id)
    again.close()
    assert len(replayed) == 1
    assert replayed[0].underlying == "SPX"
    assert replayed[0].score == result.rows[0].score
    assert replayed[0].call_wall == result.rows[0].call_wall
    assert stored_basis is not None
    assert stored_basis.basis == basis.basis
    assert stored_basis.method == "last_rth_close"
    assert stored_basis.future_symbol == "ES"
