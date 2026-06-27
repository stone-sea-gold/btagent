"""Portfolio management API routes."""

import json

from fastapi import APIRouter

from src.api.dependencies import get_services
from src.api.schemas import HoldingsSaveRequest, PositionRulesSaveRequest
from src.tools.position_tools import (
    get_portfolio_status,
    save_holdings,
    save_position_rules,
)

router = APIRouter()


@router.post("/holdings")
async def save_holdings_endpoint(req: HoldingsSaveRequest):
    """Save portfolio holdings."""
    services = get_services()
    result = save_holdings(
        session_id=req.session_id,
        holdings_json=json.dumps(req.holdings),
        manager=services.position_manager,
    )
    return result


@router.get("/{session_id}/status")
async def get_portfolio_status_endpoint(session_id: str):
    """Get portfolio status and check rule violations."""
    services = get_services()
    result = get_portfolio_status(session_id, services.position_manager)
    return result


@router.post("/rules")
async def save_position_rules_endpoint(req: PositionRulesSaveRequest):
    """Save position management rules."""
    services = get_services()
    result = save_position_rules(
        session_id=req.session_id,
        rules_json=json.dumps(req.rules),
        manager=services.position_manager,
    )
    return result
