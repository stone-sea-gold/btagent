"""Data coverage API routes."""

import json

from fastapi import APIRouter

from src.tools.data_tools import check_data_coverage

router = APIRouter()


@router.get("/coverage")
async def check_coverage_endpoint():
    """Check Qlib data coverage and freshness."""
    result = check_data_coverage()
    return json.loads(result) if isinstance(result, str) else result
