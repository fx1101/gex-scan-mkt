# SPDX-License-Identifier: Apache-2.0
"""SQLite snapshot store. Stdlib only. Replay returns the rows that were saved."""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path

from gex_scanner.scanner.scan import ExpiryBar, RankRow, StrikeBar
from gex_scanner.sessions.basis import SessionBasis

_SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshots (
    snapshot_id TEXT PRIMARY KEY,
    underlying TEXT NOT NULL,
    captured_at_utc TEXT NOT NULL,
    chain_json TEXT,
    basis_json TEXT,
    row_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    underlying TEXT,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


def _row_to_json(row: RankRow) -> dict:
    payload = {
        "underlying": row.underlying,
        "snapshot_id": row.snapshot_id,
        "vendor": row.vendor,
        "score": row.score,
        "components": row.components,
        "regime_sign": row.regime_sign,
        "regime_hypothesis": row.regime_hypothesis,
        "net_gex": row.net_gex,
        "abs_net_gex": row.abs_net_gex,
        "spot": row.spot,
        "reference_price": row.reference_price,
        "reference_symbol": row.reference_symbol,
        "flip": row.flip,
        "call_wall": row.call_wall,
        "put_wall": row.put_wall,
        "dte_call_wall": row.dte_call_wall,
        "dte_put_wall": row.dte_put_wall,
        "distance_flip_points": row.distance_flip_points,
        "distance_flip_pct": row.distance_flip_pct,
        "distance_call_points": row.distance_call_points,
        "distance_call_pct": row.distance_call_pct,
        "distance_put_points": row.distance_put_points,
        "distance_put_pct": row.distance_put_pct,
        "zero_dte_gross_share": row.zero_dte_gross_share,
        "futures_symbol": row.futures_symbol,
        "futures_flip": row.futures_flip,
        "futures_call_wall": row.futures_call_wall,
        "futures_put_wall": row.futures_put_wall,
        "futures_dte_call_wall": row.futures_dte_call_wall,
        "futures_dte_put_wall": row.futures_dte_put_wall,
        "basis": row.basis,
        "basis_method": row.basis_method,
        "snapshot_session_key": row.snapshot_session_key,
        "active_session_key": row.active_session_key,
        "session_ct": row.session_ct,
        "session_et": row.session_et,
        "captured_at_utc": row.captured_at_utc,
        "data_age_seconds": row.data_age_seconds,
        "contracts_seen": row.contracts_seen,
        "contracts_included": row.contracts_included,
        "quality_flags": list(row.quality_flags),
        "reused_us_map": row.reused_us_map,
        "note": row.note,
        "badge": row.badge,
        "strikes": [
            {
                "strike": bar.strike,
                "call_gex": bar.call_gex,
                "put_gex": bar.put_gex,
                "net_gex": bar.net_gex,
            }
            for bar in row.strikes
        ],
        "expiries": [{"expiry": bar.expiry, "net_gex": bar.net_gex} for bar in row.expiries],
        "unit": row.unit,
        "disclaimer": row.disclaimer,
    }
    return payload


def row_from_json(payload: dict) -> RankRow:
    return RankRow(
        underlying=payload["underlying"],
        snapshot_id=payload["snapshot_id"],
        vendor=payload["vendor"],
        score=payload["score"],
        components=dict(payload["components"]),
        regime_sign=payload["regime_sign"],
        regime_hypothesis=payload["regime_hypothesis"],
        net_gex=payload["net_gex"],
        abs_net_gex=payload["abs_net_gex"],
        spot=payload["spot"],
        reference_price=payload["reference_price"],
        reference_symbol=payload["reference_symbol"],
        flip=payload["flip"],
        call_wall=payload["call_wall"],
        put_wall=payload["put_wall"],
        dte_call_wall=payload["dte_call_wall"],
        dte_put_wall=payload["dte_put_wall"],
        distance_flip_points=payload["distance_flip_points"],
        distance_flip_pct=payload["distance_flip_pct"],
        distance_call_points=payload["distance_call_points"],
        distance_call_pct=payload["distance_call_pct"],
        distance_put_points=payload["distance_put_points"],
        distance_put_pct=payload["distance_put_pct"],
        zero_dte_gross_share=payload["zero_dte_gross_share"],
        futures_symbol=payload["futures_symbol"],
        futures_flip=payload["futures_flip"],
        futures_call_wall=payload["futures_call_wall"],
        futures_put_wall=payload["futures_put_wall"],
        futures_dte_call_wall=payload["futures_dte_call_wall"],
        futures_dte_put_wall=payload["futures_dte_put_wall"],
        basis=payload["basis"],
        basis_method=payload["basis_method"],
        snapshot_session_key=payload["snapshot_session_key"],
        active_session_key=payload["active_session_key"],
        session_ct=payload["session_ct"],
        session_et=payload["session_et"],
        captured_at_utc=payload["captured_at_utc"],
        data_age_seconds=payload["data_age_seconds"],
        contracts_seen=payload["contracts_seen"],
        contracts_included=payload["contracts_included"],
        quality_flags=tuple(payload["quality_flags"]),
        reused_us_map=payload["reused_us_map"],
        note=payload["note"],
        badge=payload["badge"],
        strikes=tuple(
            StrikeBar(
                strike=item["strike"],
                call_gex=item["call_gex"],
                put_gex=item["put_gex"],
                net_gex=item["net_gex"],
            )
            for item in payload["strikes"]
        ),
        expiries=tuple(
            ExpiryBar(expiry=item["expiry"], net_gex=item["net_gex"])
            for item in payload["expiries"]
        ),
        unit=payload["unit"],
        disclaimer=payload["disclaimer"],
    )


class SnapshotStore:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._connection = sqlite3.connect(self.path, check_same_thread=False)
        self._connection.executescript(_SCHEMA)

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def save_scan(
        self,
        rows: tuple[RankRow, ...] | list[RankRow],
        chains: dict | None = None,
    ) -> None:
        chains = chains or {}
        with self._lock:
            for row in rows:
                basis = None
                if row.basis is not None and row.futures_symbol is not None and row.basis_method:
                    basis = {
                        "index_symbol": row.underlying,
                        "future_symbol": row.futures_symbol,
                        "index_level": row.spot,
                        "future_level": row.spot + row.basis,
                        "basis": row.basis,
                        "method": row.basis_method,
                    }
                chain = chains.get(row.underlying)
                chain_json = None if chain is None else chain.raw_json
                self._connection.execute(
                    """
                    INSERT INTO snapshots (
                        snapshot_id, underlying, captured_at_utc,
                        chain_json, basis_json, row_json
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(snapshot_id) DO UPDATE SET
                        underlying = excluded.underlying,
                        captured_at_utc = excluded.captured_at_utc,
                        chain_json = excluded.chain_json,
                        basis_json = excluded.basis_json,
                        row_json = excluded.row_json
                    """,
                    (
                        row.snapshot_id,
                        row.underlying,
                        row.captured_at_utc,
                        chain_json,
                        None if basis is None else json.dumps(basis),
                        json.dumps(_row_to_json(row)),
                    ),
                )
            self._connection.commit()

    def replay(self, underlying: str) -> list[RankRow]:
        with self._lock:
            cursor = self._connection.execute(
                """
                SELECT row_json FROM snapshots
                WHERE underlying = ?
                ORDER BY captured_at_utc, snapshot_id
                """,
                (underlying,),
            )
            return [row_from_json(json.loads(row[0])) for row in cursor]

    def basis_for(self, snapshot_id: str) -> SessionBasis | None:
        with self._lock:
            cursor = self._connection.execute(
                "SELECT basis_json FROM snapshots WHERE snapshot_id = ?",
                (snapshot_id,),
            )
            found = cursor.fetchone()
        if found is None or found[0] is None:
            return None
        payload = json.loads(found[0])
        return SessionBasis(
            index_symbol=payload["index_symbol"],
            future_symbol=payload["future_symbol"],
            index_level=payload["index_level"],
            future_level=payload["future_level"],
            basis=payload["basis"],
            method=payload["method"],
        )

    def latest_rows(self) -> list[RankRow]:
        with self._lock:
            cursor = self._connection.execute(
                """
                SELECT row_json FROM snapshots AS outer_row
                WHERE captured_at_utc = (
                    SELECT MAX(captured_at_utc) FROM snapshots
                    WHERE underlying = outer_row.underlying
                )
                """
            )
            rows = [row_from_json(json.loads(item[0])) for item in cursor]
        rows.sort(key=lambda row: (-row.score, row.underlying))
        return rows

    def latest(self, underlying: str) -> RankRow | None:
        found = self.replay(underlying)
        if not found:
            return None
        return found[-1]

    def save_alert(self, payload: dict) -> None:
        with self._lock:
            self._connection.execute(
                """
                INSERT INTO alerts (kind, underlying, payload_json, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    str(payload.get("event", "")),
                    payload.get("underlying"),
                    json.dumps(payload),
                    datetime.now(UTC).isoformat(),
                ),
            )
            self._connection.commit()

    def alerts(self) -> list[dict]:
        with self._lock:
            cursor = self._connection.execute("SELECT payload_json FROM alerts ORDER BY id")
            return [json.loads(row[0]) for row in cursor]
