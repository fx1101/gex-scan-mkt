# SPDX-License-Identifier: Apache-2.0
"""File-backed chains for tests and the offline quick start.

The loader does not open sockets. ``expected`` blocks in a fixture are
ignored by the engine; tests read them separately.
"""

from __future__ import annotations

import gzip
import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from gex_scanner.types import ChainSnapshot, Contract, FutureQuote

CT = ZoneInfo("America/Chicago")
_RIGHTS = {"call", "put"}


def _require(payload: dict[str, Any], key: str, path: Path) -> Any:
    if key not in payload:
        raise ValueError(f"{path}: missing {key}")
    return payload[key]


def _aware(value: str, path: Path, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{path}: {field} is not an ISO datetime") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{path}: {field} must include a timezone offset")
    return parsed


def _optional_float(value: Any, path: Path, field: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{path}: {field} must be a number or null")
    return float(value)


def _contract(raw: dict[str, Any], path: Path) -> Contract:
    right = str(_require(raw, "right", path)).lower()
    if right not in _RIGHTS:
        raise ValueError(f"{path}: right must be call or put, got {right!r}")
    flow = raw.get("flow_sign")
    if flow is not None and flow not in (1, -1):
        raise ValueError(f"{path}: flow_sign must be 1, -1, or null")
    quote_time = None
    if raw.get("quote_time"):
        quote_time = _aware(str(raw["quote_time"]), path, "quote_time")
    flags = raw.get("provider_flags") or []
    if not isinstance(flags, list) or not all(isinstance(flag, str) for flag in flags):
        raise ValueError(f"{path}: provider_flags must be a list of strings")
    expiry_raw = str(_require(raw, "expiry", path))
    try:
        expiry = date.fromisoformat(expiry_raw)
    except ValueError as exc:
        raise ValueError(f"{path}: expiry must be YYYY-MM-DD") from exc
    return Contract(
        occ_symbol=str(_require(raw, "occ_symbol", path)),
        root=str(_require(raw, "root", path)),
        expiry=expiry,
        dte=int(_require(raw, "dte", path)),
        right=right,
        strike=float(_require(raw, "strike", path)),
        multiplier=float(_require(raw, "multiplier", path)),
        exercise_style=str(_require(raw, "exercise_style", path)),
        settlement=raw.get("settlement"),
        bid=_optional_float(raw.get("bid"), path, "bid"),
        ask=_optional_float(raw.get("ask"), path, "ask"),
        last=_optional_float(raw.get("last"), path, "last"),
        volume=_optional_float(raw.get("volume"), path, "volume"),
        open_interest=_optional_float(raw.get("open_interest"), path, "open_interest"),
        iv=_optional_float(raw.get("iv"), path, "iv"),
        delta=_optional_float(raw.get("delta"), path, "delta"),
        gamma=_optional_float(raw.get("gamma"), path, "gamma"),
        theta=_optional_float(raw.get("theta"), path, "theta"),
        vega=_optional_float(raw.get("vega"), path, "vega"),
        rho=_optional_float(raw.get("rho"), path, "rho"),
        quote_time=quote_time,
        deliverable=raw.get("deliverable"),
        non_standard=bool(raw.get("non_standard", False)),
        non_standard_reason=raw.get("non_standard_reason"),
        expiry_kind=raw.get("expiry_kind"),
        flow_sign=None if flow is None else int(flow),
        provider_flags=tuple(flags),
    )


def _future(raw: dict[str, Any], path: Path) -> FutureQuote:
    quote_time = None
    if raw.get("quote_time"):
        quote_time = _aware(str(raw["quote_time"]), path, "futures.quote_time")
    return FutureQuote(
        symbol=str(_require(raw, "symbol", path)),
        price=float(_require(raw, "price", path)),
        quote_time=quote_time,
    )


def load_chain_file(path: Path | str) -> ChainSnapshot:
    """Load one fixture JSON file. Does not contact a network."""

    file_path = Path(path)
    raw_json = file_path.read_text(encoding="utf-8")
    payload = json.loads(raw_json)
    if not isinstance(payload, dict):
        raise ValueError(f"{file_path}: fixture root must be an object")
    captured = _aware(str(_require(payload, "captured_at", file_path)), file_path, "captured_at")
    contracts_raw = _require(payload, "contracts", file_path)
    if not isinstance(contracts_raw, list) or not contracts_raw:
        raise ValueError(f"{file_path}: contracts must be a non-empty list")
    futures_raw = payload.get("futures") or []
    return ChainSnapshot(
        vendor=str(_require(payload, "vendor", file_path)),
        snapshot_id=str(_require(payload, "snapshot_id", file_path)),
        captured_at_utc=captured.astimezone(UTC),
        captured_at_ct=captured.astimezone(CT),
        underlying=str(_require(payload, "underlying", file_path)),
        spot=float(_require(payload, "spot", file_path)),
        spot_field=str(payload.get("spot_field") or "spot"),
        contracts=tuple(_contract(item, file_path) for item in contracts_raw),
        futures=tuple(_future(item, file_path) for item in futures_raw),
        raw_json=raw_json,
    )


def raw_cache_path(root: Path, vendor: str, symbol: str, snapshot_id: str) -> Path:
    """Cache key: vendor + symbol + snapshot_id."""

    return Path(root) / vendor / symbol / f"{snapshot_id}.json.gz"


def write_raw_cache(snapshot: ChainSnapshot, root: Path | str) -> Path:
    """Gzip the original payload. Refuses to invent a payload."""

    if not snapshot.raw_json:
        raise ValueError(f"{snapshot.snapshot_id} has no raw payload to cache")
    path = raw_cache_path(Path(root), snapshot.vendor, snapshot.underlying, snapshot.snapshot_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wb") as handle:
        handle.write(snapshot.raw_json.encode("utf-8"))
    return path


def read_raw_cache(path: Path | str) -> str:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        return handle.read()


class FixtureProvider:
    """``ChainProvider`` backed by a JSON file or a directory of JSON files."""

    vendor = "fixture"

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)

    def get_chain(self, underlying: str, snapshot_id: str | None = None) -> ChainSnapshot:
        if self.root.is_file():
            snapshot = load_chain_file(self.root)
            if snapshot.underlying != underlying:
                raise KeyError(f"{self.root} is {snapshot.underlying}, not {underlying}")
            if snapshot_id is not None and snapshot.snapshot_id != snapshot_id:
                raise KeyError(
                    f"{self.root} snapshot_id is {snapshot.snapshot_id}, not {snapshot_id}"
                )
            return snapshot
        matches: list[ChainSnapshot] = []
        for file_path in sorted(self.root.glob("*.json")):
            snapshot = load_chain_file(file_path)
            if snapshot.underlying != underlying:
                continue
            if snapshot_id is not None and snapshot.snapshot_id != snapshot_id:
                continue
            matches.append(snapshot)
        if len(matches) != 1:
            raise KeyError(
                f"expected one fixture for {underlying!r} snapshot_id={snapshot_id!r}, "
                f"found {len(matches)} under {self.root}"
            )
        return matches[0]
