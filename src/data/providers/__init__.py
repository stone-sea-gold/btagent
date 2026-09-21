"""Data provider adapters.

Each module adapts one external source to the canonical models in
:mod:`src.data.schema`, and registers itself by name in :data:`PROVIDERS` so the
sync layer can build a chain from a priority string.

Providers hold an authenticated session, and establishing one is expensive on
some sources — BaoStock's login alone measured 75-78s here. Instances are
therefore shared process-wide through :func:`get_provider` instead of being
rebuilt for every sync, so that cost is paid once rather than per run.
"""

from __future__ import annotations

import threading

from src.data.provider import DataProvider
from src.data.providers.baostock import BaoStockProvider
from src.exceptions import DataSourceError

PROVIDERS: dict[str, type] = {
    BaoStockProvider.name: BaoStockProvider,
}

_instances: dict[str, DataProvider] = {}
_lock = threading.Lock()


def get_provider(name: str) -> DataProvider:
    """The shared provider for ``name``, built on first use.

    Sharing is the point: a per-sync instance re-authenticates every time, while
    a shared one authenticates once per process.

    Raises:
        DataSourceError: ``name`` is not a registered source.
    """
    with _lock:
        instance = _instances.get(name)
        if instance is None:
            factory = PROVIDERS.get(name)
            if factory is None:
                raise DataSourceError(
                    f"unknown data source {name!r}; available: {sorted(PROVIDERS)}"
                )
            instance = factory()
            _instances[name] = instance
        return instance


def reset_provider(name: str) -> None:
    """Drop the shared provider for ``name`` so the next call re-authenticates."""
    with _lock:
        instance = _instances.pop(name, None)
    if instance is not None:
        instance.close()


def close_providers() -> None:
    """Close every shared session; call at shutdown."""
    with _lock:
        instances = list(_instances.values())
        _instances.clear()
    for instance in instances:
        instance.close()


__all__ = [
    "PROVIDERS",
    "BaoStockProvider",
    "close_providers",
    "get_provider",
    "reset_provider",
]
