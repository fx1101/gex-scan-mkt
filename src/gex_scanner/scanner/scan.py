# SPDX-License-Identifier: Apache-2.0
"""Scan a universe of chains into a ranked table. No network and no orders."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime

from gex_scanner.adapters.fixtures import FixtureProvider
from gex_scanner.config import EngineConfig, ExpiryFilter
from gex_scanner.engine.flip import compute_flip
from gex_scanner.engine.gex import compute_symbol_gex
from gex_scanner.scanner.ranker import (
    REUSED_US_MAP,
    STALE_SECONDS,
    UNVALIDATED,
    WALL_OVERLAP_PCT,
    RankWeights,
    percent_distance,
    regime_hypothesis,
    regime_sign,
    research_components,
    research_score,
)
from gex_scanner.scanner.universe import Universe
from gex_scanner.sessions.basis import SessionBasis, map_levels
from gex_scanner.sessions.calendar import session_at
from gex_scanner.types import ChainSnapshot, StrikeGex

_WATCH = frozenset({"asia_watch", "london_watch"})


@dataclass(frozen=True)
class StrikeBar:
    strike: float
    call_gex: float
    put_gex: float
    net_gex: float


@dataclass(frozen=True)
class ExpiryBar:
    expiry: str
    net_gex: float


@dataclass(frozen=True)
class RankRow:
    underlying: str
    snapshot_id: str
    vendor: str
    score: float
    components: dict[str, float]
    regime_sign: str
    regime_hypothesis: str
    net_gex: float
    abs_net_gex: float
    spot: float
    reference_price: float
    reference_symbol: str
    flip: float | None
    call_wall: float | None
    put_wall: float | None
    dte_call_wall: float | None
    dte_put_wall: float | None
    distance_flip_points: float | None
    distance_flip_pct: float | None
    distance_call_points: float | None
    distance_call_pct: float | None
    distance_put_points: float | None
    distance_put_pct: float | None
    zero_dte_gross_share: float | None
    futures_symbol: str | None
    futures_flip: float | None
    futures_call_wall: float | None
    futures_put_wall: float | None
    futures_dte_call_wall: float | None
    futures_dte_put_wall: float | None
    basis: float | None
    basis_method: str | None
    snapshot_session_key: str
    active_session_key: str
    session_ct: str
    session_et: str
    captured_at_utc: str
    data_age_seconds: float
    contracts_seen: int
    contracts_included: int
    quality_flags: tuple[str, ...]
    reused_us_map: bool
    note: str
    badge: str
    strikes: tuple[StrikeBar, ...]
    expiries: tuple[ExpiryBar, ...]
    unit: str
    disclaimer: str


@dataclass(frozen=True)
class ScanResult:
    rows: tuple[RankRow, ...]
    skipped: tuple[str, ...]
    active_session_key: str
    as_of: datetime


def _wall_strike(wall) -> float | None:
    if wall is None:
        return None
    return float(wall.strike)


def _bars(strikes: tuple[StrikeGex, ...]) -> tuple[StrikeBar, ...]:
    return tuple(
        StrikeBar(
            strike=item.strike,
            call_gex=item.call_gex,
            put_gex=item.put_gex,
            net_gex=item.net_gex,
        )
        for item in strikes
    )


def _expiries(gex) -> tuple[ExpiryBar, ...]:
    totals: dict[str, float] = {}
    for contract in gex.contracts:
        key = contract.expiry.isoformat()
        totals[key] = totals.get(key, 0.0) + contract.gex_signed
    return tuple(ExpiryBar(expiry=key, net_gex=totals[key]) for key in sorted(totals))


def _flags(quality) -> tuple[str, ...]:
    found: set[str] = set()
    for assessment in (*quality.excluded, *quality.warnings):
        found.update(assessment.flags)
    return tuple(sorted(found))


def _distance(level: float | None, reference: float) -> tuple[float | None, float | None]:
    if level is None:
        return None, None
    points = level - reference
    return points, percent_distance(level, reference)


def _prepare(
    snapshot: ChainSnapshot,
    *,
    as_of: datetime,
    active_session: str,
    basis: SessionBasis | None,
    config: EngineConfig,
) -> dict:
    gex = compute_symbol_gex(snapshot, config)
    zero = compute_symbol_gex(snapshot, replace(config, expiry_filter=ExpiryFilter.ZERO_DTE))
    flip = compute_flip(snapshot, config)
    label = session_at(snapshot.captured_at_utc, snapshot.underlying)
    reused = active_session in _WATCH
    mapped = None
    if basis is not None and basis.index_symbol == snapshot.underlying:
        mapped = map_levels(
            basis,
            flip=flip.primary_flip,
            call_wall=_wall_strike(gex.call_wall),
            put_wall=_wall_strike(gex.put_wall),
            dte_call_wall=_wall_strike(zero.call_wall),
            dte_put_wall=_wall_strike(zero.put_wall),
        )
    if reused and mapped is not None:
        reference = basis.future_level
        reference_symbol = mapped.future_symbol
        flip_level = mapped.flip
        call_level = mapped.call_wall
        put_level = mapped.put_wall
    else:
        reference = snapshot.spot
        reference_symbol = snapshot.underlying
        flip_level = flip.primary_flip
        call_level = _wall_strike(gex.call_wall)
        put_level = _wall_strike(gex.put_wall)
    distances = [
        _distance(level, reference)[1]
        for level in (flip_level, call_level, put_level)
        if level is not None
    ]
    nearest = None if not distances else min(abs(item) for item in distances)
    overlap = nearest is not None and any(
        item is not None and abs(item) <= WALL_OVERLAP_PCT
        for item in (
            _distance(call_level, reference)[1],
            _distance(put_level, reference)[1],
        )
    )
    age = (as_of - snapshot.captured_at_utc).total_seconds()
    sign = regime_sign(gex.net_gex)
    flip_points, flip_pct = _distance(flip_level, reference)
    call_points, call_pct = _distance(call_level, reference)
    put_points, put_pct = _distance(put_level, reference)
    return {
        "snapshot": snapshot,
        "gex": gex,
        "abs_net_gex": abs(gex.net_gex),
        "nearest_level_pct": nearest,
        "zero_dte_gross_share": gex.zero_dte_gross_share,
        "age_seconds": age,
        "wall_overlap": overlap,
        "sign": sign,
        "flip": flip.primary_flip,
        "call_wall": _wall_strike(gex.call_wall),
        "put_wall": _wall_strike(gex.put_wall),
        "dte_call_wall": _wall_strike(zero.call_wall),
        "dte_put_wall": _wall_strike(zero.put_wall),
        "reference": reference,
        "reference_symbol": reference_symbol,
        "distance_flip_points": flip_points,
        "distance_flip_pct": flip_pct,
        "distance_call_points": call_points,
        "distance_call_pct": call_pct,
        "distance_put_points": put_points,
        "distance_put_pct": put_pct,
        "mapped": mapped,
        "label": label,
        "reused": reused,
        "strikes": _bars(gex.strikes),
        "expiries": _expiries(gex),
        "flags": _flags(gex.quality),
    }


def scan_universe(
    chains: Mapping[str, ChainSnapshot | None],
    universe: Universe,
    *,
    as_of: datetime,
    active_session: str,
    bases: Mapping[str, SessionBasis] | None = None,
    config: EngineConfig | None = None,
    weights: RankWeights | None = None,
    stale_seconds: float = STALE_SECONDS,
) -> ScanResult:
    """Rank the symbols that have a chain. Missing symbols are skipped."""

    if as_of.tzinfo is None:
        raise ValueError("as_of must be timezone-aware")
    engine = config or EngineConfig()
    rank_weights = weights or RankWeights()
    basis_map = bases or {}
    prepared: list[dict] = []
    skipped: list[str] = []
    for symbol in universe.symbols():
        snapshot = chains.get(symbol)
        if snapshot is None:
            skipped.append(symbol)
            continue
        prepared.append(
            _prepare(
                snapshot,
                as_of=as_of,
                active_session=active_session,
                basis=basis_map.get(symbol),
                config=engine,
            )
        )
    max_abs = max((item["abs_net_gex"] for item in prepared), default=0.0)
    rows: list[RankRow] = []
    for item in prepared:
        gex = item["gex"]
        snapshot = item["snapshot"]
        components = research_components(
            abs_net_gex=item["abs_net_gex"],
            max_abs_net_gex=max_abs,
            nearest_level_pct=item["nearest_level_pct"],
            zero_dte_share=item["zero_dte_gross_share"],
            contracts_included=gex.quality.contracts_included,
            contracts_seen=gex.quality.contracts_seen,
            age_seconds=item["age_seconds"],
            wall_overlap=item["wall_overlap"],
            stale_seconds=stale_seconds,
        )
        mapped = item["mapped"]
        rows.append(
            RankRow(
                underlying=snapshot.underlying,
                snapshot_id=snapshot.snapshot_id,
                vendor=snapshot.vendor,
                score=research_score(components, rank_weights),
                components=components,
                regime_sign=item["sign"],
                regime_hypothesis=regime_hypothesis(item["sign"]),
                net_gex=gex.net_gex,
                abs_net_gex=item["abs_net_gex"],
                spot=snapshot.spot,
                reference_price=item["reference"],
                reference_symbol=item["reference_symbol"],
                flip=item["flip"],
                call_wall=item["call_wall"],
                put_wall=item["put_wall"],
                dte_call_wall=item["dte_call_wall"],
                dte_put_wall=item["dte_put_wall"],
                distance_flip_points=item["distance_flip_points"],
                distance_flip_pct=item["distance_flip_pct"],
                distance_call_points=item["distance_call_points"],
                distance_call_pct=item["distance_call_pct"],
                distance_put_points=item["distance_put_points"],
                distance_put_pct=item["distance_put_pct"],
                zero_dte_gross_share=item["zero_dte_gross_share"],
                futures_symbol=None if mapped is None else mapped.future_symbol,
                futures_flip=None if mapped is None else mapped.flip,
                futures_call_wall=None if mapped is None else mapped.call_wall,
                futures_put_wall=None if mapped is None else mapped.put_wall,
                futures_dte_call_wall=None if mapped is None else mapped.dte_call_wall,
                futures_dte_put_wall=None if mapped is None else mapped.dte_put_wall,
                basis=None if mapped is None else mapped.basis,
                basis_method=None if mapped is None else mapped.method,
                snapshot_session_key=item["label"].key,
                active_session_key=active_session,
                session_ct=item["label"].ct.isoformat(),
                session_et=item["label"].et.isoformat(),
                captured_at_utc=snapshot.captured_at_utc.isoformat(),
                data_age_seconds=item["age_seconds"],
                contracts_seen=gex.quality.contracts_seen,
                contracts_included=gex.quality.contracts_included,
                quality_flags=item["flags"],
                reused_us_map=item["reused"],
                note=REUSED_US_MAP if item["reused"] else "",
                badge=UNVALIDATED,
                strikes=item["strikes"],
                expiries=item["expiries"],
                unit=gex.unit,
                disclaimer=gex.disclaimer,
            )
        )
    rows.sort(key=lambda row: (-row.score, row.underlying))
    return ScanResult(
        rows=tuple(rows),
        skipped=tuple(skipped),
        active_session_key=active_session,
        as_of=as_of,
    )


def load_fixture_chains(root, symbols: tuple[str, ...]) -> dict[str, ChainSnapshot | None]:
    """Load one fixture per symbol. A missing file is a quiet skip, not an error."""

    provider = FixtureProvider(root)
    found: dict[str, ChainSnapshot | None] = {}
    for symbol in symbols:
        try:
            found[symbol] = provider.get_chain(symbol)
        except KeyError:
            found[symbol] = None
    return found
