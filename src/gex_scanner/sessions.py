# SPDX-License-Identifier: Apache-2.0
"""Session vocabulary.

The clock that labels "what session is it now?" is a later phase. These
constants are the keys that clock will use. Windows are documented in
``docs/SESSIONS.md`` and are not re-derived here.
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
