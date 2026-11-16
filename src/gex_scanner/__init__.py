# SPDX-License-Identifier: Apache-2.0
"""GEX Session Scanner.

Offline gamma-exposure research library. This package does not place orders.
"""

from gex_scanner.engine.gex import compute_symbol_gex

__version__ = "0.1.0"

__all__ = ["__version__", "compute_symbol_gex"]
