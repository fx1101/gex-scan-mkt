# SPDX-License-Identifier: Apache-2.0
"""Engine configuration. No network, no order placement."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum


class DealerSign(StrEnum):
    """How unsigned contract GEX is signed before it is summed.

    ``call_pos_put_neg`` is the default public convention (calls positive,
    puts negative). ``dealers_short_both`` is a research alternative.
    ``flow_signed`` is used only when a contract carries an explicit dealer
    flow sign. Volume is never a substitute for that sign.
    """

    CALL_POS_PUT_NEG = "call_pos_put_neg"
    DEALERS_SHORT_BOTH = "dealers_short_both"
    FLOW_SIGNED = "flow_signed"


class ExpiryFilter(StrEnum):
    ALL = "all"
    ZERO_DTE = "0dte"
    LTE_7D = "lte_7d"
    LTE_30D = "lte_30d"
    MONTHLY = "monthly"
    CUSTOM = "custom"


# Human-readable names used in the disclaimer string.
DEALER_SIGN_LABELS: dict[DealerSign, str] = {
    DealerSign.CALL_POS_PUT_NEG: "call_pos_put_neg",
    DealerSign.DEALERS_SHORT_BOTH: "dealers_short_both",
    DealerSign.FLOW_SIGNED: "flow_signed",
}

GEX_UNIT = "USD of estimated dealer delta change per 1% move"
# Flip time uses a fixed day count. It is not a market-calendar fraction.
DAY_COUNT = "ACT/365"


def disclaimer_for(dealer_sign: DealerSign) -> str:
    label = DEALER_SIGN_LABELS[dealer_sign]
    return (
        f"Estimated dealer GEX under the {label} sign convention. "
        "Not actual market-maker positions."
    )


@dataclass(frozen=True)
class EngineConfig:
    """Pure-function settings for one GEX computation.

    ``enable_second_order`` stays false. Vanna and charm are specified for a
    later phase and are not computed while this flag is off.
    """

    dealer_sign: DealerSign = DealerSign.CALL_POS_PUT_NEG
    expiry_filter: ExpiryFilter = ExpiryFilter.ALL
    custom_expiries: frozenset[date] = field(default_factory=frozenset)
    custom_dte_min: int | None = None
    custom_dte_max: int | None = None
    include_zero_oi: bool = False
    include_nonstandard: bool = False
    # When set, a quote older than this many seconds relative to captured_at
    # receives a stale_quote warning. None disables the clock comparison.
    stale_quote_seconds: float | None = None
    enable_second_order: bool = False
    # Flip repricing. The default band is ±15%, the top of the specified
    # ±10% to ±15% range. The rate is a config constant, not a live SOFR print.
    flip_band: float = 0.15
    flip_grid_points: int = 301
    risk_free_rate: float = 0.0
    dividend_yield: float = 0.0
    # ACT/365 year fraction used when a 0DTE contract has no explicit time_years.
    zero_dte_time_years: float = 1.0 / 365.0
    # Pin the spot node to vendor gamma when Black-Scholes disagrees by more
    # than max(abs, rel * |vendor gamma|).
    gamma_abs_tolerance: float = 1e-6
    gamma_rel_tolerance: float = 0.05
    # Nets smaller than this on both sides of a grid step are not a crossing.
    # This blocks float dust from inventing a flip. It is far below 1 USD.
    flip_dust: float = 1e-6

    def __post_init__(self) -> None:
        if self.enable_second_order:
            raise ValueError(
                "enable_second_order is not implemented. Leave it false until "
                "the vanna/charm phase is explicitly started."
            )
        if not 0.0 < self.flip_band < 1.0:
            raise ValueError("flip_band must be between 0 and 1, exclusive")
        if self.flip_grid_points < 3 or self.flip_grid_points % 2 == 0:
            raise ValueError("flip_grid_points must be an odd integer >= 3")
        if self.zero_dte_time_years <= 0:
            raise ValueError("zero_dte_time_years must be positive")
        if self.gamma_abs_tolerance < 0 or self.gamma_rel_tolerance < 0:
            raise ValueError("gamma tolerances must be non-negative")
        if self.flip_dust < 0:
            raise ValueError("flip_dust must be non-negative")
