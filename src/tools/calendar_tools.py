"""Trading calendar tools for the Agent."""

import json

from src.core.trading_calendar import TradingCalendar
from src.logging import get_logger

logger = get_logger("calendar_tools")

_calendar = TradingCalendar()


def get_current_date() -> str:
    """Get today's date and the latest trading day.

    Returns:
        JSON with today's date and latest trading day.
    """
    from datetime import datetime

    today = datetime.now().strftime("%Y-%m-%d")
    latest_trading_day = _calendar.get_latest_trading_day(today)

    return json.dumps({
        "today": today,
        "latest_trading_day": latest_trading_day,
        "is_trading_day": _calendar.is_trading_day(today),
        "status": "success",
    }, ensure_ascii=False, indent=2)


def resolve_relative_date(expression: str, reference_date: str = "") -> str:
    """Resolve a relative date expression to absolute date(s).

    Args:
        expression: Relative date expression (e.g., "最近一个交易日", "上个月", "今年以来").
        reference_date: Reference date (YYYY-MM-DD, optional, defaults to today).

    Returns:
        JSON with resolved date(s).
    """
    try:
        ref = reference_date if reference_date else None
        result = _calendar.parse_relative_date(expression, ref)

        if isinstance(result, tuple):
            return json.dumps({
                "expression": expression,
                "start_date": result[0],
                "end_date": result[1],
                "type": "range",
                "status": "success",
            }, ensure_ascii=False, indent=2)
        else:
            return json.dumps({
                "expression": expression,
                "date": result,
                "type": "single",
                "status": "success",
            }, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error("resolve_relative_date_error", error=str(e))
        return json.dumps({"error": str(e), "status": "error"}, ensure_ascii=False, indent=2)


def get_trading_days(start_date: str, end_date: str) -> str:
    """Get all trading days in a date range.

    Args:
        start_date: Start date (YYYY-MM-DD).
        end_date: End date (YYYY-MM-DD).

    Returns:
        JSON with list of trading days and count.
    """
    try:
        days = _calendar.get_trading_days(start_date, end_date)
        return json.dumps({
            "start_date": start_date,
            "end_date": end_date,
            "trading_days": days,
            "count": len(days),
            "status": "success",
        }, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error("get_trading_days_error", error=str(e))
        return json.dumps({"error": str(e), "status": "error"}, ensure_ascii=False, indent=2)
