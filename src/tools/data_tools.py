"""Data coverage tools for the Agent."""

import json
from pathlib import Path

from src.core.trading_calendar import TradingCalendar
from src.exceptions import BacktestError
from src.logging import get_logger

logger = get_logger("data_tools")

_calendar = TradingCalendar()


def _warehouse_summary() -> dict:
    """What the local warehouse holds, for the coverage report.

    ``MarketStore.coverage`` returns ``date`` objects, so they are stringified
    here: this payload is JSON for the model, and a raw ``date`` is not
    serializable.  The existence check keeps a diagnostic read from creating the
    database file as a side effect.
    """
    from src.config import settings
    from src.data.store import MarketStore

    if not Path(settings.market_data_db).exists():
        return {"status": "no_warehouse"}

    try:
        with MarketStore() as store:
            report = store.coverage()
    except Exception as e:  # noqa: BLE001 - the report must survive a bad store
        logger.error("warehouse_coverage_error", error=str(e))
        return {"status": "error", "error": str(e)}

    first, last = report["first_date"], report["last_date"]
    return {
        "bars": report["bars"],
        "codes": report["codes"],
        "first_date": first.isoformat() if first else None,
        "last_date": last.isoformat() if last else None,
        "factor_rows": report["factor_rows"],
        "calendar_days": report["calendar_days"],
    }


def check_data_coverage() -> str:
    """Check Qlib data coverage and freshness.

    Returns:
        JSON with data coverage info and staleness warning.
    """
    try:
        # Qlib keeps one module-global provider, so this read has to initialize
        # it rather than depend on whichever caller happened to run first.
        # Without this, the same request reports no_data on a cold process and
        # success once any other qlib-backed endpoint has been hit.
        from src.data.qlib_dataset import ensure_init

        try:
            ensure_init()
        except BacktestError:
            # No exported dataset yet — the report below says so plainly.
            pass

        coverage = _calendar.get_data_coverage()

        result = {
            "data_start_date": coverage.get("start_date"),
            "data_end_date": coverage.get("end_date"),
            "is_stale": coverage.get("is_stale", True),
            "days_behind": coverage.get("days_behind"),
            "status": coverage.get("status", "unknown"),
            # The warehouse totals sit alongside the dataset window so one call
            # answers "what data do we actually have?".
            "warehouse": _warehouse_summary(),
        }

        if coverage.get("is_stale"):
            result["warning"] = (
                f"数据滞后 {coverage.get('days_behind', '?')} 天。"
                f"最新数据截至 {coverage.get('end_date', '未知')}。"
                f"如需使用最新数据，请运行 `python cli.py --sync-data` 同步后"
                f"再 `python cli.py --export-qlib` 导出。"
            )

        return json.dumps(result, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error("check_data_coverage_error", error=str(e))
        return json.dumps({"error": str(e), "status": "error"}, ensure_ascii=False, indent=2)
