# SPDX-License-Identifier: Apache-2.0
"""Expiry filters. 0DTE stays inside the ``all`` view."""

from __future__ import annotations

from datetime import date

from gex_scanner.config import EngineConfig, ExpiryFilter
from gex_scanner.types import Contract


def is_third_friday(day: date) -> bool:
    """True when ``day`` is the third Friday of its calendar month."""

    return day.weekday() == 4 and 15 <= day.day <= 21


def is_monthly(contract: Contract) -> bool:
    """Monthly if the contract says so, otherwise if expiry is the third Friday.

    An explicit ``expiry_kind`` wins. A weekly that happens to fall on the
    third Friday stays a weekly when ``expiry_kind`` is ``weekly``.
    """

    if contract.expiry_kind is not None:
        return contract.expiry_kind == "monthly"
    return is_third_friday(contract.expiry)


def in_expiry_filter(contract: Contract, config: EngineConfig) -> bool:
    filt = config.expiry_filter
    if filt is ExpiryFilter.ALL:
        return True
    if filt is ExpiryFilter.ZERO_DTE:
        return contract.dte == 0
    if filt is ExpiryFilter.LTE_7D:
        return contract.dte <= 7
    if filt is ExpiryFilter.LTE_30D:
        return contract.dte <= 30
    if filt is ExpiryFilter.MONTHLY:
        return is_monthly(contract)
    if filt is ExpiryFilter.CUSTOM:
        has_dates = bool(config.custom_expiries)
        has_bounds = config.custom_dte_min is not None or config.custom_dte_max is not None
        if not has_dates and not has_bounds:
            raise ValueError("custom expiry filter requires expiries or DTE bounds")
        if has_dates and contract.expiry not in config.custom_expiries:
            return False
        if config.custom_dte_min is not None and contract.dte < config.custom_dte_min:
            return False
        if config.custom_dte_max is not None and contract.dte > config.custom_dte_max:
            return False
        return True
    raise ValueError(f"unknown expiry filter: {filt!r}")
