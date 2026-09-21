"""Market-data synchronization adapters.

These let the agent run the warehouse pipeline (sync from a data source, export
the Qlib dataset) as part of a conversation, instead of requiring the user to
step out to a shell.  Coverage reporting lives in the calendar domain, where the
date-handling flow already depends on it.
"""

from __future__ import annotations

import json
from datetime import date, timedelta

from src.agent.deps import AgentDeps
from src.agent.registry import ToolRegistry
from src.config import settings
from src.exceptions import DataSourceError
from src.logging import get_logger

logger = get_logger("data_domain")

DOMAIN = "data"


def _ok(**payload: object) -> str:
    return json.dumps({"status": "success", **payload}, ensure_ascii=False, indent=2)


def _resolve_window(
    start_date: str, end_date: str, years: int
) -> tuple[date, date]:
    # A trading window is bounded by exchange calendar dates, not instants.
    end = date.fromisoformat(end_date) if end_date else date.today()  # noqa: DTZ011
    start = date.fromisoformat(start_date) if start_date else end - timedelta(days=365 * years)
    return start, end


def register(registry: ToolRegistry, deps: AgentDeps) -> None:
    """Register market-data tools."""

    @registry.tool(DOMAIN)
    def _sync_market_data(
        index: str = "",
        codes: str = "",
        start_date: str = "",
        end_date: str = "",
        years: int = settings.years_sync_default,
        source: str = "",
    ) -> str:
        """Sync market data from a source into the local warehouse."""
        from src.data.providers import PROVIDERS, get_provider
        from src.data.store import MarketStore
        from src.data.sync import resolve_codes, sync_calendar, sync_codes

        requested = [c.strip() for c in codes.split(",") if c.strip()]
        want_index = index.strip() or (settings.default_sync_index if not requested else "")
        source_name = source.strip() or settings.data_source_priority.split(",")[0].strip()
        if source_name not in PROVIDERS:
            raise DataSourceError(
                f"unknown data source {source_name!r}; available: {sorted(PROVIDERS)}"
            )
        # A trading window is bounded by exchange calendar dates, not instants.
        end = date.fromisoformat(end_date) if end_date else date.today()  # noqa: DTZ011
        start = date.fromisoformat(start_date) if start_date else end - timedelta(days=365 * years)

        provider = get_provider(source_name)
        with MarketStore() as store:
            # An empty codes list is not the same as "no codes given".
            selected = resolve_codes(provider, index=want_index or None, codes=requested or None)
            result = sync_codes(store, provider, selected, start, end)
            result.calendar_days = sync_calendar(store, provider, start, end)

        payload = {
            "codes_requested": result.codes_requested,
            "codes_synced": result.codes_synced,
            "codes_skipped": result.codes_skipped,
            "codes_failed": result.codes_failed,
            "bars_written": result.bars_written,
            "factors_written": result.factors_written,
            "elapsed_seconds": round(result.elapsed_seconds, 1),
            "summary": result.summary(),
        }
        if result.failures:
            payload["failures"] = result.failures
        return _ok(**payload)

    @registry.tool(DOMAIN)
    def _export_qlib_dataset(out_dir: str = "") -> str:
        """Export the warehouse as a Qlib dataset the backtest reads."""
        from src.data.qlib_export import write_qlib_dataset
        from src.data.store import MarketStore

        target = out_dir.strip() or settings.qlib_export_path
        with MarketStore() as store:
            counts = write_qlib_dataset(
                store, target, exclude_from_universe=[settings.benchmark_code]
            )
        return _ok(
            out_dir=str(target),
            instruments=counts["instruments"],
            features=counts["features"],
            days=counts["days"],
            fields=counts["fields"],
        )


__all__ = ["DOMAIN", "register"]
