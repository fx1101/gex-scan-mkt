# SPDX-License-Identifier: Apache-2.0
"""Shared builders for offline tests. Not a pytest plugin."""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from gex_scanner.types import ChainSnapshot, Contract

FIXTURES = Path(__file__).parent / "fixtures"
TOLERANCE = 1.0


def assert_within_unit(actual: float, expected: float, tol: float = TOLERANCE) -> None:
    difference = abs(actual - expected)
    assert difference <= tol, f"{actual} vs {expected} differs by {difference}"


def make_contract(**overrides) -> Contract:
    captured = datetime(2026, 11, 16, 15, 0, tzinfo=UTC)
    base = dict(
        occ_symbol="TEST261116C00100000",
        root="TEST",
        expiry=date(2026, 11, 16),
        dte=0,
        right="call",
        strike=100.0,
        multiplier=100.0,
        exercise_style="american",
        settlement="physical",
        bid=1.0,
        ask=1.1,
        last=1.05,
        volume=1.0,
        open_interest=10.0,
        iv=0.2,
        delta=0.5,
        gamma=0.02,
        theta=-0.01,
        vega=0.1,
        rho=0.01,
        quote_time=captured,
        deliverable="100 TEST",
        non_standard=False,
        non_standard_reason=None,
        expiry_kind="weekly",
        flow_sign=None,
        provider_flags=(),
    )
    base.update(overrides)
    return Contract(**base)


def make_snapshot(
    contracts: list[Contract],
    *,
    spot: float = 100.0,
    underlying: str = "TEST",
) -> ChainSnapshot:
    captured = datetime(2026, 11, 16, 15, 0, tzinfo=UTC)
    return ChainSnapshot(
        vendor="unit",
        snapshot_id="unit-001",
        captured_at_utc=captured,
        captured_at_ct=captured.astimezone(ZoneInfo("America/Chicago")),
        underlying=underlying,
        spot=spot,
        spot_field="spot",
        contracts=tuple(contracts),
    )
