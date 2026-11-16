# SPDX-License-Identifier: Apache-2.0
"""Contract quality rules for the default GEX scan."""

from __future__ import annotations

from gex_scanner.config import DealerSign, EngineConfig
from gex_scanner.types import Contract, ContractAssessment

MISSING_GAMMA = "missing_gamma"
MISSING_IV = "missing_iv"
MISSING_OI = "missing_oi"
ZERO_OI = "zero_oi"
ZERO_IV = "zero_iv"
NON_STANDARD_MULTIPLIER = "non_standard_multiplier"
NON_STANDARD_DELIVERABLE = "non_standard_deliverable"
NON_STANDARD = "non_standard"
MISSING_FLOW_SIGN = "missing_flow_sign"
INVALID_MULTIPLIER = "invalid_multiplier"
INVALID_OI = "invalid_oi"
INVALID_DTE = "invalid_dte"
STALE_QUOTE = "stale_quote"

_NONSTANDARD_FLAGS = {
    NON_STANDARD,
    NON_STANDARD_MULTIPLIER,
    NON_STANDARD_DELIVERABLE,
}


def _nonstandard_flag(contract: Contract) -> str:
    reason = contract.non_standard_reason
    if reason == "multiplier":
        return NON_STANDARD_MULTIPLIER
    if reason == "deliverable":
        return NON_STANDARD_DELIVERABLE
    return NON_STANDARD


def assess_contract(
    contract: Contract,
    config: EngineConfig,
    *,
    captured_at_utc,
) -> ContractAssessment:
    """Decide whether a contract enters the default sum, and why.

    Missing gamma is an exclusion, not a silent zero. Missing IV is a warning
    on a contract that still has usable gamma. A non-standard multiplier is
    carried on the contract and left out of the default scan.
    """

    flags: list[str] = []
    for flag in contract.provider_flags:
        if flag not in flags:
            flags.append(flag)
    exclusions: list[str] = []

    if contract.dte < 0:
        flags.append(INVALID_DTE)
        exclusions.append(INVALID_DTE)

    if contract.multiplier <= 0:
        flags.append(INVALID_MULTIPLIER)
        exclusions.append(INVALID_MULTIPLIER)

    if contract.open_interest is None:
        flags.append(MISSING_OI)
        exclusions.append(MISSING_OI)
    elif contract.open_interest < 0:
        flags.append(INVALID_OI)
        exclusions.append(INVALID_OI)
    elif contract.open_interest == 0:
        flags.append(ZERO_OI)
        if not config.include_zero_oi:
            exclusions.append(ZERO_OI)

    if contract.gamma is None:
        flags.append(MISSING_GAMMA)
        exclusions.append(MISSING_GAMMA)

    if contract.iv is None:
        flags.append(MISSING_IV)
    elif contract.iv == 0:
        flags.append(ZERO_IV)

    if contract.non_standard:
        flag = _nonstandard_flag(contract)
        if flag not in flags:
            flags.append(flag)
        if not config.include_nonstandard:
            exclusions.append(flag)

    if config.dealer_sign is DealerSign.FLOW_SIGNED and contract.flow_sign not in (1, -1):
        flags.append(MISSING_FLOW_SIGN)
        exclusions.append(MISSING_FLOW_SIGN)

    if (
        config.stale_quote_seconds is not None
        and contract.quote_time is not None
        and captured_at_utc is not None
    ):
        age = (captured_at_utc - contract.quote_time).total_seconds()
        if age > config.stale_quote_seconds and STALE_QUOTE not in flags:
            flags.append(STALE_QUOTE)

    include = not exclusions
    return ContractAssessment(
        occ_symbol=contract.occ_symbol,
        include=include,
        flags=tuple(flags),
        exclusion_reasons=tuple(exclusions),
    )


def is_nonstandard_assessment(assessment: ContractAssessment) -> bool:
    return any(flag in _NONSTANDARD_FLAGS for flag in assessment.flags)
