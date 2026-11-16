# SPDX-License-Identifier: Apache-2.0
"""Normalized chain and GEX result types.

Vendors map into these records. The engine does not read vendor payloads.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any


@dataclass(frozen=True)
class Contract:
    """One option contract on a normalized chain snapshot."""

    occ_symbol: str
    root: str
    expiry: date
    dte: int
    right: str
    strike: float
    multiplier: float
    exercise_style: str
    settlement: str | None
    bid: float | None
    ask: float | None
    last: float | None
    volume: float | None
    open_interest: float | None
    iv: float | None
    delta: float | None
    gamma: float | None
    theta: float | None
    vega: float | None
    rho: float | None
    quote_time: datetime | None
    deliverable: str | None = None
    non_standard: bool = False
    non_standard_reason: str | None = None
    expiry_kind: str | None = None
    # +1 dealer long gamma, -1 dealer short gamma. Only for flow_signed.
    flow_sign: int | None = None
    provider_flags: tuple[str, ...] = ()
    # Year fraction for Black-Scholes. None means derive it from dte.
    time_years: float | None = None
    # Continuous dividend yield. None means the config default.
    dividend_yield: float | None = None


@dataclass(frozen=True)
class FutureQuote:
    symbol: str
    price: float
    quote_time: datetime | None = None


@dataclass(frozen=True)
class ChainSnapshot:
    """Normalized chain. ``raw_json`` is the provider payload, kept intact."""

    vendor: str
    snapshot_id: str
    captured_at_utc: datetime
    captured_at_ct: datetime
    underlying: str
    spot: float
    spot_field: str
    contracts: tuple[Contract, ...]
    futures: tuple[FutureQuote, ...] = ()
    raw_json: str | None = None


@dataclass(frozen=True)
class ContractAssessment:
    occ_symbol: str
    include: bool
    flags: tuple[str, ...]
    exclusion_reasons: tuple[str, ...]


@dataclass(frozen=True)
class QualityReport:
    included: tuple[str, ...]
    excluded: tuple[ContractAssessment, ...]
    warnings: tuple[ContractAssessment, ...]
    nonstandard_appendix: tuple[ContractAssessment, ...]
    contracts_seen: int
    contracts_included: int
    contracts_excluded: int


@dataclass(frozen=True)
class ContractGex:
    occ_symbol: str
    strike: float
    right: str
    expiry: date
    dte: int
    multiplier: float
    open_interest: float
    gamma: float
    gex_unsigned: float
    gex_signed: float
    flags: tuple[str, ...]


@dataclass(frozen=True)
class StrikeGex:
    strike: float
    call_gex: float
    put_gex: float
    net_gex: float
    gross_gex: float


@dataclass(frozen=True)
class Wall:
    """A strike extremum. ``gex`` is unsigned side GEX, or gross GEX for the magnet.

    ``spot_side`` records where the strike sits relative to the snapshot spot.
    Walls are not moved to the other side of spot.
    """

    strike: float
    gex: float
    kind: str
    spot_side: str


@dataclass(frozen=True)
class SymbolGex:
    """GEX for one underlying under one config.

    ``net_gex`` and the strike profile use the active expiry filter.
    The ``book_*`` fields describe every quality-eligible contract on the
    snapshot, before that filter, so 0DTE share stays comparable across views.
    """

    underlying: str
    snapshot_id: str
    vendor: str
    spot: float
    spot_field: str
    dealer_sign: str
    expiry_filter: str
    unit: str
    disclaimer: str
    net_gex: float
    call_gex: float
    put_gex: float
    gross_gex: float
    contracts: tuple[ContractGex, ...]
    strikes: tuple[StrikeGex, ...]
    call_wall: Wall | None
    put_wall: Wall | None
    gross_magnet: Wall | None
    book_zero_dte_signed_net: float
    book_signed_net: float
    book_zero_dte_gross: float
    book_gross: float
    # abs(book 0DTE signed net) / abs(book signed net), before the expiry filter.
    # None when the eligible book nets to zero.
    zero_dte_abs_net_share: float | None
    # 0DTE unsigned GEX / eligible unsigned GEX. None when the book has no GEX.
    zero_dte_gross_share: float | None
    quality: QualityReport
    raw_payload: Any = None


@dataclass(frozen=True)
class GammaResidual:
    """Vendor gamma versus Black-Scholes gamma at the snapshot spot."""

    occ_symbol: str
    vendor_gamma: float
    bs_gamma: float
    residual: float
    used_vendor_gamma_at_spot: bool


@dataclass(frozen=True)
class FlipCrossing:
    """One interpolated spot where the repriced net GEX changes sign or hits zero."""

    spot: float
    gex_left: float
    gex_right: float


@dataclass(frozen=True)
class FlipResult:
    """Zero-gamma crossings from repricing. Empty when the band does not cross."""

    underlying: str
    snapshot_spot: float
    expiry_filter: str
    band: float
    band_low: float
    band_high: float
    grid_points: int
    day_count: str
    risk_free_rate: float
    dividend_yield: float
    crossings: tuple[FlipCrossing, ...]
    primary_flip: float | None
    no_crossing_in_band: bool
    curve_net_at_spot: float
    vendor_net_at_spot: float
    residuals: tuple[GammaResidual, ...]
    skipped: tuple[tuple[str, str], ...]
    grid_spots: tuple[float, ...]
    grid_net: tuple[float, ...]
    unit: str
    disclaimer: str
