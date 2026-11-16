# SPDX-License-Identifier: Apache-2.0
"""Research rank. Each component is visible. A zero weight turns it off.

The score is not a profit forecast. Sign text states a hedging hypothesis.
"""

from __future__ import annotations

from dataclasses import dataclass

# A level within this many percent of the reference counts as overlapping a wall.
WALL_OVERLAP_PCT = 0.2
# Proximity falls from 1 to 0 across this percent distance.
PROXIMITY_SPAN_PCT = 5.0
# Net GEX inside this many USD of the documented unit is treated as flat.
SIGN_DUST = 1.0
STALE_SECONDS = 900.0

POSITIVE_HYPOTHESIS = (
    "Positive net GEX is a hypothesis that hedging is more likely to dampen moves."
)
NEGATIVE_HYPOTHESIS = (
    "Negative net GEX is a hypothesis that hedging is more likely to amplify moves."
)
FLAT_HYPOTHESIS = "Net GEX is near zero. No dampen or amplify hypothesis is stated."
UNVALIDATED = "unvalidated hypothesis"
REUSED_US_MAP = "Reused the last US GEX map. Not live Asia options GEX."

COMPONENT_NAMES = (
    "regime_size",
    "proximity",
    "zero_dte_share",
    "quality",
    "wall_overlap",
)


@dataclass(frozen=True)
class RankWeights:
    """Weights at or below zero disable that component. The row still shows it."""

    regime_size: float = 1.0
    proximity: float = 1.0
    zero_dte_share: float = 1.0
    quality: float = 1.0
    wall_overlap: float = 1.0

    def as_dict(self) -> dict[str, float]:
        return {
            "regime_size": self.regime_size,
            "proximity": self.proximity,
            "zero_dte_share": self.zero_dte_share,
            "quality": self.quality,
            "wall_overlap": self.wall_overlap,
        }


def regime_sign(net_gex: float) -> str:
    if abs(net_gex) <= SIGN_DUST:
        return "flat"
    if net_gex > 0:
        return "positive"
    return "negative"


def regime_hypothesis(sign: str) -> str:
    if sign == "positive":
        return POSITIVE_HYPOTHESIS
    if sign == "negative":
        return NEGATIVE_HYPOTHESIS
    return FLAT_HYPOTHESIS


def research_components(
    *,
    abs_net_gex: float,
    max_abs_net_gex: float,
    nearest_level_pct: float | None,
    zero_dte_share: float | None,
    contracts_included: int,
    contracts_seen: int,
    age_seconds: float | None,
    wall_overlap: bool,
    stale_seconds: float = STALE_SECONDS,
) -> dict[str, float]:
    """Map one symbol onto the five documented components, each in ``[0, 1]``."""

    if max_abs_net_gex > 0:
        regime = min(1.0, abs_net_gex / max_abs_net_gex)
    else:
        regime = 0.0
    if nearest_level_pct is None:
        proximity = 0.0
    else:
        proximity = max(0.0, 1.0 - abs(nearest_level_pct) / PROXIMITY_SPAN_PCT)
    share = 0.0 if zero_dte_share is None else min(1.0, max(0.0, zero_dte_share))
    fraction = 0.0 if contracts_seen <= 0 else contracts_included / contracts_seen
    if age_seconds is None or age_seconds <= 0:
        freshness = 1.0
    elif age_seconds >= stale_seconds:
        freshness = 0.0
    else:
        freshness = 1.0 - age_seconds / stale_seconds
    quality = 0.5 * fraction + 0.5 * freshness
    return {
        "regime_size": regime,
        "proximity": proximity,
        "zero_dte_share": share,
        "quality": quality,
        "wall_overlap": 1.0 if wall_overlap else 0.0,
    }


def research_score(components: dict[str, float], weights: RankWeights) -> float:
    """Weighted mean of the enabled components. All-zero weights score 0."""

    total = 0.0
    weight_sum = 0.0
    for name, weight in weights.as_dict().items():
        if weight <= 0:
            continue
        total += weight * components[name]
        weight_sum += weight
    if weight_sum == 0:
        return 0.0
    return total / weight_sum


def percent_distance(level: float, reference: float) -> float:
    """Signed distance as a percent of ``reference``."""

    if reference == 0:
        raise ValueError("reference price must be non-zero")
    return (level - reference) / reference * 100.0
