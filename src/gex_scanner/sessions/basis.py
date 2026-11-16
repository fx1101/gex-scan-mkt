# SPDX-License-Identifier: Apache-2.0
"""Session basis between a cash index and its future.

``futures_level = index_level + basis``, with basis equal to future minus
cash. The record stores the basis and the method so a replay uses the same
number. This module does not fetch quotes.
"""

from __future__ import annotations

from dataclasses import dataclass

# Pairs named in the 2026-11-15 research note. No other mapping is implied.
FUTURES_BY_INDEX: dict[str, str] = {
    "SPX": "ES",
    "NDX": "NQ",
    "RUT": "RTY",
}

_METHODS = frozenset({"last_rth_close", "live_future_minus_cash"})


@dataclass(frozen=True)
class SessionBasis:
    """One persisted basis. ``basis`` is future minus cash index."""

    index_symbol: str
    future_symbol: str
    index_level: float
    future_level: float
    basis: float
    method: str


def session_basis(
    index_symbol: str,
    index_level: float,
    future_level: float,
    method: str,
) -> SessionBasis:
    """Build a basis record. ``method`` is stored and not inferred later."""

    symbol = index_symbol.upper()
    if symbol not in FUTURES_BY_INDEX:
        known = ", ".join(sorted(FUTURES_BY_INDEX))
        raise ValueError(f"no futures pair is documented for {index_symbol}; known: {known}")
    if method not in _METHODS:
        raise ValueError(f"basis method must be one of {sorted(_METHODS)}")
    return SessionBasis(
        index_symbol=symbol,
        future_symbol=FUTURES_BY_INDEX[symbol],
        index_level=index_level,
        future_level=future_level,
        basis=future_level - index_level,
        method=method,
    )


def futures_level(index_level: float, basis: SessionBasis) -> float:
    """Re-express a cash level with the stored basis. Does not recompute it."""

    return index_level + basis.basis


@dataclass(frozen=True)
class MappedLevels:
    """Cash GEX levels shifted by one stored basis. Absent levels stay absent."""

    future_symbol: str
    basis: float
    method: str
    flip: float | None
    call_wall: float | None
    put_wall: float | None
    dte_call_wall: float | None
    dte_put_wall: float | None


def map_levels(
    basis: SessionBasis,
    *,
    flip: float | None,
    call_wall: float | None,
    put_wall: float | None,
    dte_call_wall: float | None = None,
    dte_put_wall: float | None = None,
) -> MappedLevels:
    """Apply ``futures_level = index_level + basis`` to each level that exists."""

    def _shift(level: float | None) -> float | None:
        if level is None:
            return None
        return futures_level(level, basis)

    return MappedLevels(
        future_symbol=basis.future_symbol,
        basis=basis.basis,
        method=basis.method,
        flip=_shift(flip),
        call_wall=_shift(call_wall),
        put_wall=_shift(put_wall),
        dte_call_wall=_shift(dte_call_wall),
        dte_put_wall=_shift(dte_put_wall),
    )
