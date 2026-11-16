# SPDX-License-Identifier: Apache-2.0
"""Research universe. TOML so the seed file needs no extra package."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Universe:
    """Indexes, then ETFs, then stocks. Order is the scan order before rank."""

    indexes: tuple[str, ...]
    etfs: tuple[str, ...]
    stocks: tuple[str, ...]

    def symbols(self) -> tuple[str, ...]:
        seen: set[str] = set()
        ordered: list[str] = []
        for name in (*self.indexes, *self.etfs, *self.stocks):
            symbol = name.strip().upper()
            if not symbol or symbol in seen:
                continue
            seen.add(symbol)
            ordered.append(symbol)
        return tuple(ordered)


def _symbols(payload: dict, key: str, path: Path) -> tuple[str, ...]:
    raw = payload.get(key, [])
    if not isinstance(raw, list) or not all(isinstance(item, str) for item in raw):
        raise ValueError(f"{path}: {key} must be a list of strings")
    return tuple(raw)


def load_universe(path: Path | str) -> Universe:
    file_path = Path(path)
    payload = tomllib.loads(file_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{file_path}: universe root must be a table")
    return Universe(
        indexes=_symbols(payload, "indexes", file_path),
        etfs=_symbols(payload, "etfs", file_path),
        stocks=_symbols(payload, "stocks", file_path),
    )
