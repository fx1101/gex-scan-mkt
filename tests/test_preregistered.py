# SPDX-License-Identifier: Apache-2.0
"""Pre-registered checks. Constructed rows are scorer inputs, not market history."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from gex_scanner.backtest.preregistered import (
    PeekError,
    SessionRecord,
    badge_for,
    build_report,
    flip_test,
    inventory_history,
    regime_test,
    render_markdown,
    run_preregistered,
)
from gex_scanner.dashboard.render import render_index

ROOT = Path(__file__).resolve().parents[1]
CT = ZoneInfo("America/Chicago")


def _day(offset: int, *, oos: bool) -> date:
    start = date(2026, 6, 1) if oos else date(2025, 6, 1)
    return start + timedelta(days=offset)


def _record(offset: int, **overrides) -> SessionRecord:
    session_date = overrides.pop("session_date", _day(offset, oos=True))
    open_at = datetime(
        session_date.year,
        session_date.month,
        session_date.day,
        8,
        30,
        tzinfo=CT,
    )
    fields = {
        "symbol": "SPX",
        "session_date": session_date,
        "session_kind": "us_rth",
        "level_time": open_at - timedelta(minutes=5),
        "window_start": open_at,
        "flip": 6000.0,
        "call_wall": 6100.0,
        "put_wall": 5900.0,
        "net_gex": 1_000_000.0,
        "zero_dte_gross_share": 0.2,
        "open": 6000.0,
        "high": 6010.0,
        "low": 5990.0,
        "close": 6005.0,
        "crossed_flip": False,
        "cross_sign": None,
        "follow_through": 0.0,
        "vix_or_atm_iv": 15.0,
    }
    fields.update(overrides)
    return SessionRecord(**fields)


def test_empty_history_is_inconclusive_and_matches_the_report() -> None:
    history = inventory_history(ROOT)
    assert history["chain_sessions"] == 0
    assert history["paired_ohlc_sessions"] == 0
    assert history["massive_key_set"] is False
    assert history["thetadata_username_set"] is False
    report = build_report(ROOT)
    assert report["badge"] == "unvalidated hypothesis"
    assert report["passed_count"] == 0
    assert {item["verdict"] for item in report["tests"]} == {"inconclusive"}
    text = render_markdown(report)
    assert "2025-05-17" in text
    assert "2026-11-17" in text
    assert "America/Chicago" in text
    assert "Chain sessions with a level at time t and a later session path: 0." in text
    page = render_index([], badge=report["badge"])
    assert "unvalidated hypothesis" in page
    committed = (ROOT / "docs" / "backtests" / "2026-11-17-validation.json").read_text(
        encoding="utf-8"
    )
    assert '"chain_sessions": 0' in committed
    assert '"passed_count": 0' in committed


def test_a_level_after_the_open_is_rejected() -> None:
    when = datetime(2026, 6, 2, 9, 0, tzinfo=CT)
    with pytest.raises(PeekError):
        SessionRecord(
            symbol="SPX",
            session_date=date(2026, 6, 2),
            session_kind="us_rth",
            level_time=when,
            window_start=when - timedelta(minutes=1),
        )


def test_small_and_noisy_samples_do_not_pass() -> None:
    small = [_record(index) for index in range(10)]
    assert flip_test(small).verdict == "inconclusive"
    noisy = []
    for index in range(70):
        noisy.append(
            _record(
                index,
                crossed_flip=True,
                cross_sign=1,
                follow_through=0.0001,
            )
        )
        noisy.append(
            _record(
                index,
                session_date=_day(index + 80, oos=True),
                crossed_flip=False,
                cross_sign=None,
                follow_through=0.0,
            )
        )
    result = flip_test(noisy)
    assert result.verdict == "fail"
    assert result.passed is False
    missing_iv = [
        _record(index, vix_or_atm_iv=None, net_gex=1_000_000.0 if index % 2 == 0 else -1_000_000.0)
        for index in range(160)
    ]
    assert regime_test(missing_iv).verdict == "inconclusive"


def test_a_large_constructed_effect_can_clear_the_flip_bar() -> None:
    """Scorer check only. These rows are not written into the dated report."""

    rows = []
    for index in range(80):
        rows.append(
            _record(
                index,
                crossed_flip=True,
                cross_sign=1,
                follow_through=0.02,
            )
        )
        rows.append(
            _record(
                index,
                session_date=_day(index + 100, oos=True),
                crossed_flip=False,
                cross_sign=None,
                follow_through=0.0,
            )
        )
    result = flip_test(rows)
    assert result.verdict == "pass"
    whole = run_preregistered(rows)
    assert badge_for(whole) == "unvalidated hypothesis"
