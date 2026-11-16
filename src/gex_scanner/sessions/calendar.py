# SPDX-License-Identifier: Apache-2.0
"""America/Chicago session clock.

Exchange windows are the ET hours in ``docs/SESSIONS.md``. Membership is
decided by converting an aware instant to America/New_York and America/Chicago
with ``zoneinfo``, so DST gaps and folds stay on the real timeline.

``asia_watch`` is 09:00–15:00 Asia/Tokyo on a Tokyo weekday.
``london_watch`` is 08:00–16:30 Europe/London on a London weekday.
Those windows are clock hours, not a JPX or LSE holiday calendar.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from gex_scanner.sessions.holidays import EARLY_CLOSES, EARLY_OPTIONS_CLOSE_ET, FULL_CLOSES
from gex_scanner.sessions.keys import (
    DESIGNATED_ETF_UNDERLYINGS,
    EQUITY_PREMARKET_UNDERLYINGS,
    GTH_INDEX_UNDERLYINGS,
)

CT = ZoneInfo("America/Chicago")
ET = ZoneInfo("America/New_York")
LONDON = ZoneInfo("Europe/London")
TOKYO = ZoneInfo("Asia/Tokyo")

# ET windows from the research note, as seconds from midnight. Ends are exclusive.
_RTH_OPEN = 9 * 3600 + 30 * 60
_RTH_EQUITY_CLOSE = 16 * 3600
_RTH_INDEX_CLOSE = 16 * 3600 + 15 * 60
_CURB_INDEX_CLOSE = 17 * 3600
_PRE_OPEN = 7 * 3600 + 30 * 60
_PRE_CLOSE = 9 * 3600 + 25 * 60
_POST_OPEN = 16 * 3600
_POST_CLOSE = 16 * 3600 + 15 * 60
_GTH_OPEN = 20 * 3600 + 15 * 60
_GTH_CLOSE = 9 * 3600 + 25 * 60
_EARLY_CLOSE = EARLY_OPTIONS_CLOSE_ET[0] * 3600 + EARLY_OPTIONS_CLOSE_ET[1] * 60

_LONDON_OPEN = 8 * 3600
_LONDON_CLOSE = 16 * 3600 + 30 * 60
_TOKYO_OPEN = 9 * 3600
_TOKYO_CLOSE = 15 * 3600

_PRIORITY = (
    "us_rth",
    "us_curb",
    "us_equity_pre",
    "us_gth_index",
    "asia_watch",
    "london_watch",
)

WATCH_DESCRIPTION = "Reuse the last valid US GEX map. Not a live options book."

_PREMARKET = frozenset(EQUITY_PREMARKET_UNDERLYINGS)
_GTH = frozenset(GTH_INDEX_UNDERLYINGS)
_DESIGNATED = frozenset(DESIGNATED_ETF_UNDERLYINGS)


@dataclass(frozen=True)
class SessionLabel:
    """Label for one instant and one underlying."""

    key: str | None
    also_active: tuple[str, ...]
    ct: datetime
    et: datetime
    underlying: str
    options_session: bool
    watch_only: bool
    description: str


def _seconds(moment: datetime) -> int:
    return moment.hour * 3600 + moment.minute * 60 + moment.second


def _inside(moment: datetime, start: int, end: int) -> bool:
    clock = _seconds(moment)
    return start <= clock < end


def _weekday(moment: datetime) -> bool:
    return moment.weekday() < 5


def _in_gth(et: datetime) -> bool:
    if et.date() in FULL_CLOSES:
        return False
    clock = _seconds(et)
    if clock >= _GTH_OPEN:
        # Sunday through Thursday evenings. Friday evening waits for Sunday.
        return et.weekday() in {6, 0, 1, 2, 3}
    if clock < _GTH_CLOSE:
        return et.weekday() in {0, 1, 2, 3, 4}
    return False


def _in_tokyo(moment: datetime) -> bool:
    tokyo = moment.astimezone(TOKYO)
    return _weekday(tokyo) and _inside(tokyo, _TOKYO_OPEN, _TOKYO_CLOSE)


def _in_london(moment: datetime) -> bool:
    london = moment.astimezone(LONDON)
    return _weekday(london) and _inside(london, _LONDON_OPEN, _LONDON_CLOSE)


def session_at(when: datetime, underlying: str) -> SessionLabel:
    """Return the primary session for ``underlying`` at ``when``.

    A trading session outranks a watch session. ``local_asia`` and
    ``local_london`` are never selected. ``key`` is None when nothing matches.
    """

    if when.tzinfo is None:
        raise ValueError("session clock requires a timezone-aware datetime")
    symbol = underlying.upper()
    ct = when.astimezone(CT)
    et = when.astimezone(ET)
    holiday = et.date() in FULL_CLOSES
    early = et.date() in EARLY_CLOSES
    trading_day = _weekday(et) and not holiday
    active: list[str] = []

    rth_close = _RTH_INDEX_CLOSE if symbol in _GTH or symbol in _DESIGNATED else _RTH_EQUITY_CLOSE
    if symbol == "NDX":
        rth_close = _RTH_INDEX_CLOSE
    if early:
        rth_close = _EARLY_CLOSE
    if trading_day and _inside(et, _RTH_OPEN, rth_close):
        active.append("us_rth")

    index_curb = symbol in _GTH and _inside(et, _RTH_INDEX_CLOSE, _CURB_INDEX_CLOSE)
    equity_curb = symbol in (_PREMARKET - _DESIGNATED) and _inside(et, _POST_OPEN, _POST_CLOSE)
    if trading_day and not early and (index_curb or equity_curb):
        active.append("us_curb")

    if trading_day and symbol in _PREMARKET and _inside(et, _PRE_OPEN, _PRE_CLOSE):
        active.append("us_equity_pre")

    if symbol in _GTH and _in_gth(et):
        active.append("us_gth_index")

    if _in_tokyo(when):
        active.append("asia_watch")
    if _in_london(when):
        active.append("london_watch")

    ordered = tuple(key for key in _PRIORITY if key in active)
    key = ordered[0] if ordered else None
    watch_only = key in {"asia_watch", "london_watch"}
    options_session = key in {"us_rth", "us_curb", "us_equity_pre", "us_gth_index"}
    if key is None:
        description = "No US options session and no watch window."
    elif watch_only:
        description = WATCH_DESCRIPTION
    else:
        description = f"US options session {key}."
    return SessionLabel(
        key=key,
        also_active=ordered,
        ct=ct,
        et=et,
        underlying=symbol,
        options_session=options_session,
        watch_only=watch_only,
        description=description,
    )
