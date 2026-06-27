"""Data coverage tools for the Agent."""

import json

from src.core.trading_calendar import TradingCalendar
from src.logging import get_logger

logger = get_logger("data_tools")

_calendar = TradingCalendar()


def check_data_coverage() -> str:
    """Check Qlib data coverage and freshness.

    Returns:
        JSON with data coverage info and staleness warning.
    """
    try:
        coverage = _calendar.get_data_coverage()

        result = {
            "data_start_date": coverage.get("start_date"),
            "data_end_date": coverage.get("end_date"),
            "is_stale": coverage.get("is_stale", True),
            "days_behind": coverage.get("days_behind"),
            "status": coverage.get("status", "unknown"),
        }

        if coverage.get("is_stale"):
            result["warning"] = (
                f"数据滞后 {coverage.get('days_behind', '?')} 天。"
                f"最新数据截至 {coverage.get('end_date', '未知')}。"
                f"如需使用最新数据，请运行 `python cli.py --init-data` 更新。"
            )

        return json.dumps(result, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error("check_data_coverage_error", error=str(e))
        return json.dumps({"error": str(e), "status": "error"}, ensure_ascii=False, indent=2)
