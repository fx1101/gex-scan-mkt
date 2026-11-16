# SPDX-License-Identifier: Apache-2.0
"""Dashboard HTML shows the ranked table, bars, and the unvalidated badge."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from gex_scanner.dashboard.render import render_index, render_symbol
from gex_scanner.scanner import load_fixture_chains, load_universe, scan_universe

ROOT = Path(__file__).resolve().parents[1]


def test_dashboard_renders_ranked_setups_and_a_strike_profile() -> None:
    universe = load_universe(ROOT / "config" / "universe.toml")
    chains = load_fixture_chains(ROOT / "tests" / "fixtures", universe.symbols())
    result = scan_universe(
        chains,
        universe,
        as_of=datetime(2026, 11, 16, 15, 0, tzinfo=UTC),
        active_session="us_rth",
    )
    page = render_index(list(result.rows))
    assert "Ranked setups" in page
    assert "unvalidated hypothesis" in page
    assert "SPX" in page
    assert "SPY" in page
    banned = " ".join(("best", "most", "profitable"))
    assert banned not in page.lower()
    symbol = render_symbol(result.rows[0])
    assert "GEX by strike" in symbol
    assert "Expiry breakdown" in symbol
    assert 'class="bar' in symbol
    assert "unvalidated hypothesis" in symbol
