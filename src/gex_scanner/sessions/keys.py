# SPDX-License-Identifier: Apache-2.0
"""Session keys and the equity lists the clock is allowed to use.

Hours are not stored here. The clock converts the ET schedule in
``docs/SESSIONS.md``.
"""

from __future__ import annotations

# Order matches docs/SESSIONS.md.
SESSION_KEYS: tuple[str, ...] = (
    "us_rth",
    "us_curb",
    "us_gth_index",
    "us_equity_pre",
    "asia_watch",
    "london_watch",
    "local_asia",
    "local_london",
)

# Disabled until a non-US options adapter exists.
DISABLED_SESSION_KEYS: tuple[str, ...] = ("local_asia", "local_london")

# Cboe extended-hours launch list dated 2026-10-19, as recorded in the
# project research note. This is the seed for us_equity_pre, not a claim
# that every name trades every session.
EQUITY_PREMARKET_UNDERLYINGS: tuple[str, ...] = (
    "AAPL",
    "AMD",
    "AMZN",
    "AVGO",
    "BABA",
    "BAC",
    "F",
    "GLD",
    "GOOG",
    "GOOGL",
    "HOOD",
    "INTC",
    "IWM",
    "META",
    "MRVL",
    "MSFT",
    "MU",
    "NFLX",
    "NOK",
    "NVDA",
    "ORCL",
    "PFE",
    "PLTR",
    "QQQ",
    "SNDK",
    "SPY",
    "TSLA",
    "TSM",
    "XLF",
)

# GTH product list from the 2026-11-15 research note. NDX was not on it.
GTH_INDEX_UNDERLYINGS: tuple[str, ...] = ("SPX", "XSP", "VIX", "RUT")

# The same note names SPY and QQQ as designated ETFs/ETNs whose RTH runs
# until 4:15 PM ET. It does not publish the rest of that designated list.
DESIGNATED_ETF_UNDERLYINGS: tuple[str, ...] = ("SPY", "QQQ")

# Index URL form on the Cboe delayed CDN uses a leading underscore.
# NDX and DJX are included because the research note shows that form for
# index symbols. NDX is still RTH-primary for the session clock.
CBOE_INDEX_UNDERLYINGS: tuple[str, ...] = (
    "SPX",
    "NDX",
    "RUT",
    "VIX",
    "XSP",
    "DJX",
)
