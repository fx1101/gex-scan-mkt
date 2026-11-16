# SPDX-License-Identifier: Apache-2.0
"""The socket guard used by the rest of the suite."""

from __future__ import annotations

import socket

import pytest


def test_outbound_sockets_are_blocked() -> None:
    with pytest.raises(RuntimeError, match="Network calls are blocked"):
        socket.create_connection(("example.com", 80), timeout=1)
