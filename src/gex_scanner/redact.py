# SPDX-License-Identifier: Apache-2.0
"""Redact configured secrets before they reach a log line."""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Mapping
from typing import Any

SENSITIVE_ENV_NAMES: tuple[str, ...] = (
    "WEBULL_APP_KEY",
    "WEBULL_APP_SECRET",
    "MASSIVE_API_KEY",
    "THETADATA_USERNAME",
    "THETADATA_PASSWORD",
    "TRADIER_TOKEN",
    "ALERT_WEBHOOK_URL",
)


def redact(message: str, env: Mapping[str, str] | None = None) -> str:
    """Replace known secret values with ``[REDACTED]``.

    Empty values are ignored so a blank ``.env`` does not wipe the message.
    """

    source = os.environ if env is None else env
    redacted = message
    for name in SENSITIVE_ENV_NAMES:
        value = source.get(name, "")
        if value:
            redacted = redacted.replace(value, "[REDACTED]")
    return redacted


def log_event(logger: logging.Logger, event: str, **fields: Any) -> None:
    """Write one JSON object. String fields pass through :func:`redact`."""

    payload: dict[str, Any] = {"event": event}
    for key, value in fields.items():
        if isinstance(value, str):
            payload[key] = redact(value)
        else:
            payload[key] = value
    logger.info(json.dumps(payload, sort_keys=True, default=str))
