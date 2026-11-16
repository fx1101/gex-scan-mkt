# SPDX-License-Identifier: Apache-2.0
"""Repo hygiene: no secrets, no profit language, redacted logs."""

from __future__ import annotations

import logging
from pathlib import Path

from gex_scanner.redact import log_event, redact

ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {".git", ".venv", "venv", "__pycache__", ".pytest_cache"}


def _text_files():
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        suffixes = {".py", ".md", ".toml", ".yml", ".yaml", ".example", ".txt", ".json"}
        if path.suffix.lower() not in suffixes:
            if path.name not in {".env.example", ".gitignore"}:
                continue
        yield path


def test_env_example_has_empty_secrets() -> None:
    assignments = {}
    for line in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        assignments[key] = value
    assert assignments["WEBULL_APP_KEY"] == ""
    assert assignments["WEBULL_APP_SECRET"] == ""
    assert assignments["WEBULL_ENVIRONMENT"] == "sandbox"
    assert assignments["MASSIVE_API_KEY"] == ""
    assert assignments["THETADATA_USERNAME"] == ""
    assert assignments["THETADATA_PASSWORD"] == ""
    assert assignments["TRADIER_TOKEN"] == ""
    assert assignments["ALERT_WEBHOOK_URL"] == ""
    assert assignments["ENABLE_LIVE_ORDERS"] == "false"


def test_gitignore_covers_env_and_caches() -> None:
    text = (ROOT / ".gitignore").read_text(encoding="utf-8")
    for needle in (".env", "__pycache__", "token_cache", "data/raw"):
        assert needle in text


def test_no_private_key_material_or_profit_slogan() -> None:
    for path in _text_files():
        if path.name == "test_hygiene.py":
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        lowered = text.lower()
        assert "begin private key" not in lowered
        assert "best most profitable" not in lowered


def test_redact_removes_configured_secrets_from_logs(caplog, monkeypatch) -> None:
    secret = "super-secret-value"
    monkeypatch.setenv("WEBULL_APP_SECRET", secret)
    env = {"WEBULL_APP_SECRET": secret, "WEBULL_APP_KEY": ""}
    assert redact(f"header {secret} tail", env) == "header [REDACTED] tail"
    assert redact("empty key stays", env) == "empty key stays"
    logger = logging.getLogger("gex.test")
    with caplog.at_level(logging.INFO):
        log_event(logger, "snapshot", detail=f"token {secret}")
    assert secret not in caplog.text
    assert "[REDACTED]" in caplog.text
