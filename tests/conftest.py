# SPDX-License-Identifier: Apache-2.0
"""Offline tests. Sockets are blocked unless a test is marked network."""

from __future__ import annotations

import socket

import pytest


@pytest.fixture(autouse=True)
def _block_network(monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest) -> None:
    if request.node.get_closest_marker("network"):
        return

    def _blocked(*_args, **_kwargs):
        raise RuntimeError("Network calls are blocked in tests")

    monkeypatch.setattr(socket.socket, "connect", _blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", _blocked)
    monkeypatch.setattr(socket, "create_connection", _blocked)
