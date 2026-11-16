# SPDX-License-Identifier: Apache-2.0
"""Black-Scholes-Merton gamma. No I/O.

Day-count and rate policy live with the caller. This module only evaluates
the closed form at a fixed year fraction.
"""

from __future__ import annotations

import math

_SQRT_TWO_PI = math.sqrt(2.0 * math.pi)


def norm_pdf(x: float) -> float:
    """Standard normal density."""

    return math.exp(-0.5 * x * x) / _SQRT_TWO_PI


def bsm_d1(
    spot: float,
    strike: float,
    rate: float,
    dividend_yield: float,
    sigma: float,
    time_years: float,
) -> float:
    """Merton d1. ``dividend_yield`` is a continuous yield q."""

    vol_sqrt_t = sigma * math.sqrt(time_years)
    return (
        math.log(spot / strike) + (rate - dividend_yield + 0.5 * sigma * sigma) * time_years
    ) / vol_sqrt_t


def bsm_gamma(
    spot: float,
    strike: float,
    rate: float,
    dividend_yield: float,
    sigma: float,
    time_years: float,
) -> float:
    """Black-Scholes-Merton gamma per 1 unit of spot.

    gamma = exp(-q T) * n(d1) / (S * sigma * sqrt(T))

    The value is positive. Call and put gamma are the same in this model.
    """

    if spot <= 0 or strike <= 0 or sigma <= 0 or time_years <= 0:
        raise ValueError("BSM gamma needs positive spot, strike, volatility, and time")
    d1 = bsm_d1(spot, strike, rate, dividend_yield, sigma, time_years)
    return (
        math.exp(-dividend_yield * time_years)
        * norm_pdf(d1)
        / (spot * sigma * math.sqrt(time_years))
    )
