"""Calendar API routes."""

import json

from fastapi import APIRouter

from src.tools.calendar_tools import (
    get_current_date,
    get_trading_days,
    resolve_relative_date,
)

router = APIRouter()


def _parse_json(result):
    """Parse JSON string if needed."""
    return json.loads(result) if isinstance(result, str) else result


@router.get("/today")
async def get_today_endpoint():
    """Get today's date and latest trading day."""
    return _parse_json(get_current_date())


@router.get("/resolve")
async def resolve_date_endpoint(expression: str, reference_date: str = ""):
    """Resolve a relative date expression."""
    return _parse_json(resolve_relative_date(expression, reference_date))


@router.get("/trading-days")
async def get_trading_days_endpoint(start: str, end: str):
    """Get trading days in a date range."""
    return _parse_json(get_trading_days(start, end))
