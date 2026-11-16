# SPDX-License-Identifier: Apache-2.0
"""Level string for the Pine overlay. The chart does not receive a chain.

Grammar, shared with ``src/gex_scanner/tv/pine/gex_levels.pine``:

    SYMBOL|flip:<number>|call:<number>|put:<number>|dte_call:<number>|dte_put:<number>

An empty value after a colon means that level is absent. Numbers use
Python's general format so a later ``float()`` round-trips.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from gex_scanner.scanner.scan import RankRow

LEVEL_KEYS = ("flip", "call", "put", "dte_call", "dte_put")


def _num(value: float | None) -> str:
    if value is None:
        return ""
    return format(value, ".10g")


def format_level_string(
    symbol: str,
    *,
    flip: float | None,
    call_wall: float | None,
    put_wall: float | None,
    dte_call_wall: float | None,
    dte_put_wall: float | None,
) -> str:
    fields = {
        "flip": flip,
        "call": call_wall,
        "put": put_wall,
        "dte_call": dte_call_wall,
        "dte_put": dte_put_wall,
    }
    body = "|".join(f"{key}:{_num(fields[key])}" for key in LEVEL_KEYS)
    return f"{symbol}|{body}"


def format_row(row: RankRow, *, mapped: bool = False) -> str:
    if mapped:
        return format_level_string(
            row.futures_symbol or row.underlying,
            flip=row.futures_flip,
            call_wall=row.futures_call_wall,
            put_wall=row.futures_put_wall,
            dte_call_wall=row.futures_dte_call_wall,
            dte_put_wall=row.futures_dte_put_wall,
        )
    return format_level_string(
        row.underlying,
        flip=row.flip,
        call_wall=row.call_wall,
        put_wall=row.put_wall,
        dte_call_wall=row.dte_call_wall,
        dte_put_wall=row.dte_put_wall,
    )


def parse_level_string(text: str) -> dict[str, Any]:
    """Parse the exporter string the same way the Pine script splits it."""

    parts = text.strip().split("|")
    if len(parts) < 2 or not parts[0]:
        raise ValueError("level string needs a symbol and fields")
    parsed: dict[str, Any] = {"symbol": parts[0]}
    seen: list[str] = []
    for part in parts[1:]:
        if ":" not in part:
            raise ValueError(f"level field {part!r} needs a colon")
        key, value = part.split(":", 1)
        if key not in LEVEL_KEYS:
            raise ValueError(f"unknown level field {key}")
        parsed[key] = None if value == "" else float(value)
        seen.append(key)
    missing = [key for key in LEVEL_KEYS if key not in seen]
    if missing:
        raise ValueError(f"level string is missing {', '.join(missing)}")
    return parsed


def export_document(row: RankRow) -> dict[str, Any]:
    cash = format_row(row, mapped=False)
    document: dict[str, Any] = {
        "symbol": row.underlying,
        "level_string": cash,
        "parsed": parse_level_string(cash),
        "badge": row.badge,
        "places_orders": False,
        "session_key": row.snapshot_session_key,
        "session_ct": row.session_ct,
        "session_et": row.session_et,
    }
    if row.futures_symbol is not None:
        mapped = format_row(row, mapped=True)
        document["futures_symbol"] = row.futures_symbol
        document["futures_level_string"] = mapped
        document["basis"] = row.basis
        document["basis_method"] = row.basis_method
    return document


def write_export(row: RankRow, path: Path | str) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(export_document(row), indent=2) + "\n", encoding="utf-8")
    return destination
