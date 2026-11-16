# SPDX-License-Identifier: Apache-2.0
"""Session vocabulary still matches docs/SESSIONS.md. The clock is test_sessions.py."""

from __future__ import annotations

import re
from pathlib import Path

from gex_scanner.sessions import (
    DISABLED_SESSION_KEYS,
    EQUITY_PREMARKET_UNDERLYINGS,
    SESSION_KEYS,
)

ROOT = Path(__file__).resolve().parents[1]


def test_session_keys_are_the_documented_set() -> None:
    assert SESSION_KEYS == (
        "us_rth",
        "us_curb",
        "us_gth_index",
        "us_equity_pre",
        "asia_watch",
        "london_watch",
        "local_asia",
        "local_london",
    )
    text = (ROOT / "docs" / "SESSIONS.md").read_text(encoding="utf-8")
    for key in SESSION_KEYS:
        assert f"`{key}`" in text
    for key in DISABLED_SESSION_KEYS:
        assert key in SESSION_KEYS


def test_equity_premarket_seed_matches_the_documented_launch_list() -> None:
    assert len(EQUITY_PREMARKET_UNDERLYINGS) == 29
    assert len(set(EQUITY_PREMARKET_UNDERLYINGS)) == 29
    text = (ROOT / "docs" / "SESSIONS.md").read_text(encoding="utf-8")
    for symbol in EQUITY_PREMARKET_UNDERLYINGS:
        assert re.search(rf"\b{re.escape(symbol)}\b", text), symbol
