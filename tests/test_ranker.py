# SPDX-License-Identifier: Apache-2.0
"""Research rank, fixture-universe order, and ES basis mapping."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from gex_scanner.scanner import RankWeights, load_fixture_chains, load_universe, scan_universe
from gex_scanner.scanner.ranker import research_components, research_score
from gex_scanner.sessions.basis import futures_level, map_levels, session_basis

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"
GOLDEN = FIXTURES / "expected" / "ranked_universe.json"
AS_OF = datetime(2026, 11, 16, 15, 0, tzinfo=UTC)


def _fixture_scan(session: str = "us_rth", bases=None, weights=None):
    universe = load_universe(ROOT / "config" / "universe.toml")
    chains = load_fixture_chains(FIXTURES, universe.symbols())
    return scan_universe(
        chains,
        universe,
        as_of=AS_OF,
        active_session=session,
        bases=bases,
        weights=weights,
    )


def test_components_match_the_documented_weights() -> None:
    components = research_components(
        abs_net_gex=100.0,
        max_abs_net_gex=200.0,
        nearest_level_pct=2.5,
        zero_dte_share=0.25,
        contracts_included=8,
        contracts_seen=10,
        age_seconds=0.0,
        wall_overlap=True,
    )
    assert components["regime_size"] == pytest.approx(0.5)
    assert components["proximity"] == pytest.approx(0.5)
    assert components["zero_dte_share"] == pytest.approx(0.25)
    assert components["quality"] == pytest.approx(0.9)
    assert components["wall_overlap"] == 1.0
    assert research_score(components, RankWeights()) == pytest.approx(
        (0.5 + 0.5 + 0.25 + 0.9 + 1.0) / 5
    )
    disabled = research_score(components, RankWeights(regime_size=0))
    assert disabled == pytest.approx((0.5 + 0.25 + 0.9 + 1.0) / 4)


def test_known_spx_flip_maps_onto_es_with_the_stored_basis() -> None:
    basis = session_basis("SPX", 6000.0, 6012.5, "last_rth_close")
    mapped = map_levels(basis, flip=6700.0, call_wall=6800.0, put_wall=6600.0)
    assert basis.future_symbol == "ES"
    assert basis.basis == pytest.approx(12.5)
    assert mapped.flip == pytest.approx(futures_level(6700.0, basis))
    assert mapped.call_wall == pytest.approx(6812.5)
    assert mapped.put_wall == pytest.approx(6612.5)


def test_fixture_universe_rank_is_stable_and_skips_missing_names() -> None:
    first = _fixture_scan()
    second = _fixture_scan()
    assert [row.underlying for row in first.rows] == [row.underlying for row in second.rows]
    assert [row.score for row in first.rows] == [row.score for row in second.rows]
    assert "NDX" in first.skipped
    assert "RUT" in first.skipped
    assert "QQQ" in first.skipped
    assert {row.underlying for row in first.rows} == {"SPX", "SPY"}
    assert all(row.badge == "unvalidated hypothesis" for row in first.rows)
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    actual = [
        {
            "underlying": row.underlying,
            "score": round(row.score, 6),
            "regime_sign": row.regime_sign,
            "flip": None if row.flip is None else round(row.flip, 6),
            "call_wall": row.call_wall,
            "put_wall": row.put_wall,
        }
        for row in first.rows
    ]
    assert actual == golden["rows"]


def test_asia_watch_reuses_the_us_map_and_scores_the_future() -> None:
    basis = session_basis("SPX", 6000.0, 6012.5, "live_future_minus_cash")
    result = _fixture_scan("asia_watch", bases={"SPX": basis})
    spx = next(row for row in result.rows if row.underlying == "SPX")
    spy = next(row for row in result.rows if row.underlying == "SPY")
    assert spx.reused_us_map is True
    assert "Not live Asia options GEX" in spx.note
    assert spx.futures_symbol == "ES"
    assert spx.basis == pytest.approx(12.5)
    assert spx.basis_method == "live_future_minus_cash"
    if spx.flip is not None:
        assert spx.futures_flip == pytest.approx(spx.flip + 12.5)
        assert spx.reference_symbol == "ES"
    assert spy.futures_symbol is None
    assert spy.note == "Reused the last US GEX map. Not live Asia options GEX."
