# SPDX-License-Identifier: Apache-2.0
"""Provider interface. Later adapters must return ``ChainSnapshot``."""

from __future__ import annotations

from typing import Protocol

from gex_scanner.types import ChainSnapshot


class ChainProvider(Protocol):
    """A source of normalized option chains.

    Implementations keep the raw payload on the snapshot. Tests for the
    offline engine use :class:`gex_scanner.adapters.fixtures.FixtureProvider`
    and do not open sockets.
    """

    vendor: str

    def get_chain(self, underlying: str, snapshot_id: str | None = None) -> ChainSnapshot:
        """Return one snapshot for ``underlying``."""
