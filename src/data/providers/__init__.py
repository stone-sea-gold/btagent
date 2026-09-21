"""Data provider adapters.

Each module adapts one external source to the canonical models in
:mod:`src.data.schema`, and registers itself by name in :data:`PROVIDERS` so the
sync layer can build a chain from a priority string.
"""

from __future__ import annotations

from src.data.providers.baostock import BaoStockProvider

PROVIDERS: dict[str, type] = {
    BaoStockProvider.name: BaoStockProvider,
}

__all__ = ["PROVIDERS", "BaoStockProvider"]
