# SPDX-License-Identifier: Apache-2.0
"""Per-contract and per-strike dealer GEX.

The unit is USD of estimated dealer delta change per 1% move::

    gex_unsigned = abs(gamma) * OI * multiplier * spot^2 * 0.01

``multiplier`` is the contract's own multiplier. This module does not
substitute 100.
"""

from __future__ import annotations

from gex_scanner.config import (
    GEX_UNIT,
    DealerSign,
    EngineConfig,
    disclaimer_for,
)
from gex_scanner.engine.filters import in_expiry_filter
from gex_scanner.engine.quality import assess_contract, is_nonstandard_assessment
from gex_scanner.engine.walls import call_wall, gross_magnet, put_wall
from gex_scanner.types import (
    ChainSnapshot,
    Contract,
    ContractGex,
    QualityReport,
    StrikeGex,
    SymbolGex,
)


def unsigned_gex(gamma: float, open_interest: float, multiplier: float, spot: float) -> float:
    """Unsigned dollar GEX for one contract at ``spot``."""

    return abs(gamma) * open_interest * multiplier * spot * spot * 0.01


def dealer_sign_factor(contract: Contract, config: EngineConfig) -> float:
    """Map a contract to +1 or -1 under the active convention."""

    sign = config.dealer_sign
    if sign is DealerSign.CALL_POS_PUT_NEG:
        if contract.right == "call":
            return 1.0
        if contract.right == "put":
            return -1.0
        raise ValueError(f"unknown right: {contract.right!r}")
    if sign is DealerSign.DEALERS_SHORT_BOTH:
        return -1.0
    if sign is DealerSign.FLOW_SIGNED:
        if contract.flow_sign not in (1, -1):
            raise ValueError(
                f"{contract.occ_symbol} has no flow_sign; refusing to infer one from volume"
            )
        return float(contract.flow_sign)
    raise ValueError(f"unknown dealer_sign: {sign!r}")


def _aggregate_strikes(rows: list[ContractGex]) -> tuple[StrikeGex, ...]:
    by_strike: dict[float, dict[str, float]] = {}
    for row in rows:
        bucket = by_strike.setdefault(
            row.strike,
            {"call": 0.0, "put": 0.0, "net": 0.0, "gross": 0.0},
        )
        bucket["gross"] += row.gex_unsigned
        bucket["net"] += row.gex_signed
        if row.right == "call":
            bucket["call"] += row.gex_unsigned
        elif row.right == "put":
            bucket["put"] += row.gex_unsigned
    ordered = []
    for strike in sorted(by_strike):
        bucket = by_strike[strike]
        ordered.append(
            StrikeGex(
                strike=strike,
                call_gex=bucket["call"],
                put_gex=bucket["put"],
                net_gex=bucket["net"],
                gross_gex=bucket["gross"],
            )
        )
    return tuple(ordered)


def compute_symbol_gex(snapshot: ChainSnapshot, config: EngineConfig | None = None) -> SymbolGex:
    """Compute signed GEX, walls, and the quality report for one snapshot.

    Contracts that fail a quality exclusion are omitted from the sum and
    listed on the report. They are not inserted as a zero-gamma row.
    """

    if config is None:
        config = EngineConfig()
    if snapshot.spot <= 0:
        raise ValueError("spot must be positive")
    symbols = [contract.occ_symbol for contract in snapshot.contracts]
    if len(symbols) != len(set(symbols)):
        raise ValueError("duplicate occ_symbol in snapshot")

    assessments = tuple(
        assess_contract(contract, config, captured_at_utc=snapshot.captured_at_utc)
        for contract in snapshot.contracts
    )
    assessment_by_symbol = {item.occ_symbol: item for item in assessments}
    included_symbols = tuple(item.occ_symbol for item in assessments if item.include)
    excluded = tuple(item for item in assessments if not item.include)
    warnings = tuple(item for item in assessments if item.include and item.flags)
    nonstandard_appendix = tuple(item for item in assessments if is_nonstandard_assessment(item))
    quality = QualityReport(
        included=included_symbols,
        excluded=excluded,
        warnings=warnings,
        nonstandard_appendix=nonstandard_appendix,
        contracts_seen=len(snapshot.contracts),
        contracts_included=len(included_symbols),
        contracts_excluded=len(excluded),
    )

    book_signed = 0.0
    book_gross = 0.0
    book_zero_dte_signed = 0.0
    book_zero_dte_gross = 0.0
    view_rows: list[ContractGex] = []

    for contract in snapshot.contracts:
        assessment = assessment_by_symbol[contract.occ_symbol]
        if not assessment.include:
            continue
        assert contract.gamma is not None
        assert contract.open_interest is not None
        gross = unsigned_gex(
            contract.gamma,
            contract.open_interest,
            contract.multiplier,
            snapshot.spot,
        )
        signed = dealer_sign_factor(contract, config) * gross
        book_signed += signed
        book_gross += gross
        if contract.dte == 0:
            book_zero_dte_signed += signed
            book_zero_dte_gross += gross
        if not in_expiry_filter(contract, config):
            continue
        view_rows.append(
            ContractGex(
                occ_symbol=contract.occ_symbol,
                strike=contract.strike,
                right=contract.right,
                expiry=contract.expiry,
                dte=contract.dte,
                multiplier=contract.multiplier,
                open_interest=contract.open_interest,
                gamma=contract.gamma,
                gex_unsigned=gross,
                gex_signed=signed,
                flags=assessment.flags,
            )
        )

    strikes = _aggregate_strikes(view_rows)
    call_total = sum(row.gex_unsigned for row in view_rows if row.right == "call")
    put_total = sum(row.gex_unsigned for row in view_rows if row.right == "put")
    net = sum(row.gex_signed for row in view_rows)
    gross_total = sum(row.gex_unsigned for row in view_rows)
    if book_signed == 0:
        zero_dte_abs_net_share = None
    else:
        zero_dte_abs_net_share = abs(book_zero_dte_signed) / abs(book_signed)
    if book_gross == 0:
        zero_dte_gross_share = None
    else:
        zero_dte_gross_share = book_zero_dte_gross / book_gross

    return SymbolGex(
        underlying=snapshot.underlying,
        snapshot_id=snapshot.snapshot_id,
        vendor=snapshot.vendor,
        spot=snapshot.spot,
        spot_field=snapshot.spot_field,
        dealer_sign=config.dealer_sign.value,
        expiry_filter=config.expiry_filter.value,
        unit=GEX_UNIT,
        disclaimer=disclaimer_for(config.dealer_sign),
        net_gex=net,
        call_gex=call_total,
        put_gex=put_total,
        gross_gex=gross_total,
        contracts=tuple(view_rows),
        strikes=strikes,
        call_wall=call_wall(strikes, snapshot.spot),
        put_wall=put_wall(strikes, snapshot.spot),
        gross_magnet=gross_magnet(strikes, snapshot.spot),
        book_zero_dte_signed_net=book_zero_dte_signed,
        book_signed_net=book_signed,
        book_zero_dte_gross=book_zero_dte_gross,
        book_gross=book_gross,
        zero_dte_abs_net_share=zero_dte_abs_net_share,
        zero_dte_gross_share=zero_dte_gross_share,
        quality=quality,
        raw_payload=snapshot.raw_json,
    )
