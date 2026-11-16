# SPDX-License-Identifier: Apache-2.0
"""Session clock. Instants are the ones documented in docs/SESSIONS.md."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from gex_scanner.sessions import futures_level, session_at, session_basis
from gex_scanner.sessions.calendar import WATCH_DESCRIPTION

CT = ZoneInfo("America/Chicago")
UTC = ZoneInfo("UTC")


def _at(year: int, month: int, day: int, hour: int, minute: int, *, fold: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=CT, fold=fold)


def test_rth_open_is_the_et_cash_open() -> None:
    opened = session_at(_at(2026, 11, 16, 8, 30), "SPX")
    before = session_at(_at(2026, 11, 16, 8, 29), "SPY")
    assert opened.key == "us_rth"
    assert opened.et.hour == 9 and opened.et.minute == 30
    assert opened.ct.tzname() == "CST"
    assert before.key != "us_rth"
    assert "london_watch" in before.also_active


def test_index_gth_opens_sunday_evening() -> None:
    opened = session_at(_at(2026, 11, 15, 19, 15), "SPX")
    before = session_at(_at(2026, 11, 15, 19, 14), "SPX")
    equity = session_at(_at(2026, 11, 15, 19, 15), "SPY")
    assert opened.key == "us_gth_index"
    assert opened.options_session is True
    assert before.key != "us_gth_index"
    assert equity.key == "asia_watch"
    assert equity.watch_only is True
    assert equity.description == WATCH_DESCRIPTION
    assert "live Asia options" not in equity.description


def test_equity_premarket_is_only_the_launch_list() -> None:
    listed = session_at(_at(2026, 11, 16, 6, 30), "SPY")
    unlisted = session_at(_at(2026, 11, 16, 6, 30), "IBM")
    index = session_at(_at(2026, 11, 16, 6, 30), "SPX")
    assert listed.key == "us_equity_pre"
    assert unlisted.key != "us_equity_pre"
    assert index.key == "us_gth_index"


def test_ct_midnight_follows_the_tokyo_clock() -> None:
    # CST midnight is 15:00 JST, the exclusive end of the Tokyo window.
    winter = session_at(_at(2026, 1, 15, 0, 0), "SPY")
    # CDT midnight is 14:00 JST, still inside that window.
    summer = session_at(_at(2026, 7, 15, 0, 0), "SPY")
    index = session_at(_at(2026, 7, 15, 0, 0), "SPX")
    assert winter.key is None
    assert "asia_watch" not in winter.also_active
    assert summer.key == "asia_watch"
    assert index.key == "us_gth_index"
    assert "asia_watch" in index.also_active


def test_dst_spring_forward_skips_the_gap_and_recomputes_london() -> None:
    before = _at(2026, 3, 8, 1, 30)
    after = _at(2026, 3, 8, 3, 30)
    gap = _at(2026, 3, 8, 2, 30)
    assert before.utcoffset() != after.utcoffset()
    assert gap.astimezone(UTC) == after.astimezone(UTC)
    # US is already on CDT and the UK is still on GMT, so 02:30 CT is not 08:00 London.
    mismatched = session_at(_at(2026, 3, 16, 2, 30), "SPY")
    london_open = session_at(_at(2026, 3, 16, 3, 0), "SPY")
    assert mismatched.key != "london_watch"
    assert "london_watch" not in mismatched.also_active
    assert london_open.key == "london_watch"
    # March 8 2026 is a Sunday, so the 02:00 gap is before the evening GTH open.
    assert session_at(before, "SPX").key is None
    assert session_at(after, "SPX").key is None
    assert session_at(_at(2026, 3, 8, 19, 15), "SPX").key == "us_gth_index"


def test_dst_fall_back_fold_keeps_the_same_session() -> None:
    first = _at(2026, 11, 1, 1, 30, fold=0)
    second = _at(2026, 11, 1, 1, 30, fold=1)
    assert first.astimezone(UTC) != second.astimezone(UTC)
    assert (second.astimezone(UTC) - first.astimezone(UTC)).total_seconds() == 3600
    early = session_at(first, "SPX")
    late = session_at(second, "SPX")
    # November 1 2026 is a Sunday. Both folds are before the evening open.
    assert early.key is None
    assert late.key == early.key
    assert session_at(_at(2026, 11, 1, 19, 15), "SPX").key == "us_gth_index"
    # UK has already left BST, so the winter 02:00 CT rule is an hour early.
    before_london = session_at(_at(2026, 10, 26, 2, 30), "IBM")
    at_london = session_at(_at(2026, 10, 26, 3, 0), "IBM")
    assert before_london.key != "london_watch"
    assert at_london.key == "london_watch"


def test_early_close_ends_options_at_the_nyse_footnote() -> None:
    early_still_open = session_at(_at(2026, 11, 27, 12, 14), "SPX")
    early_done = session_at(_at(2026, 11, 27, 12, 15), "SPX")
    normal = session_at(_at(2026, 11, 20, 12, 15), "SPX")
    holiday = session_at(_at(2026, 11, 26, 10, 0), "SPX")
    evening_before = session_at(_at(2026, 11, 25, 19, 15), "SPX")
    holiday_morning = session_at(_at(2026, 11, 26, 7, 0), "SPX")
    assert early_still_open.key == "us_rth"
    assert early_done.key != "us_rth"
    assert "us_curb" not in early_done.also_active
    assert normal.key == "us_rth"
    assert holiday.key != "us_rth"
    assert evening_before.key == "us_gth_index"
    assert holiday_morning.key != "us_gth_index"


def test_naive_datetime_is_rejected() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        session_at(datetime(2026, 11, 16, 8, 30), "SPX")


def test_stored_basis_replays_without_refetching_the_future() -> None:
    recorded = session_basis("SPX", 6700.0, 6702.5, "last_rth_close")
    assert recorded.future_symbol == "ES"
    assert recorded.basis == pytest.approx(2.5)
    assert futures_level(6700.0, recorded) == pytest.approx(6702.5)
    assert futures_level(6710.0, recorded) == pytest.approx(6712.5)
