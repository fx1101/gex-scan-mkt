# SPDX-License-Identifier: Apache-2.0
"""Call wall, put wall, and gross-gamma magnet.

Walls use unsigned side totals. They are not forced to bracket spot.
"""

from __future__ import annotations

from collections.abc import Callable

from gex_scanner.types import StrikeGex, Wall


def _spot_side(strike: float, spot: float) -> str:
    if strike == spot:
        return "at"
    if strike > spot:
        return "above"
    return "below"


def _prefer(current: StrikeGex, challenger: StrikeGex, spot: float) -> StrikeGex:
    """Tie-break: nearer to spot, then the lower strike."""

    current_distance = abs(current.strike - spot)
    challenger_distance = abs(challenger.strike - spot)
    if challenger_distance < current_distance:
        return challenger
    if challenger_distance > current_distance:
        return current
    if challenger.strike < current.strike:
        return challenger
    return current


def select_wall(
    strikes: tuple[StrikeGex, ...] | list[StrikeGex],
    value_of: Callable[[StrikeGex], float],
    spot: float,
    kind: str,
) -> Wall | None:
    """Pick the strike with the largest positive ``value_of``.

    A zero total is not a wall. Exact ties use :func:`_prefer`.
    """

    best: StrikeGex | None = None
    best_value = 0.0
    for strike in strikes:
        value = value_of(strike)
        if value <= 0:
            continue
        if best is None or value > best_value:
            best = strike
            best_value = value
        elif value == best_value and best is not None:
            best = _prefer(best, strike, spot)
    if best is None:
        return None
    return Wall(
        strike=best.strike,
        gex=best_value,
        kind=kind,
        spot_side=_spot_side(best.strike, spot),
    )


def call_wall(strikes: tuple[StrikeGex, ...] | list[StrikeGex], spot: float) -> Wall | None:
    return select_wall(strikes, lambda row: row.call_gex, spot, "call_wall")


def put_wall(strikes: tuple[StrikeGex, ...] | list[StrikeGex], spot: float) -> Wall | None:
    return select_wall(strikes, lambda row: row.put_gex, spot, "put_wall")


def gross_magnet(strikes: tuple[StrikeGex, ...] | list[StrikeGex], spot: float) -> Wall | None:
    return select_wall(strikes, lambda row: row.gross_gex, spot, "gross_magnet")
