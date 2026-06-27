"""Stock selection API routes."""

import json

from fastapi import APIRouter

from src.api.dependencies import get_services
from src.api.schemas import SelectionRequest
from src.tools.selection_tools import select_stocks

router = APIRouter()


@router.post("/run")
async def run_selection_endpoint(req: SelectionRequest):
    """Run stock selection pipeline."""
    services = get_services()
    result = select_stocks(
        name=req.name,
        factor_ids=",".join(req.factor_ids),
        top_k=req.top_k,
        factor_weights_json=json.dumps(req.factor_weights) if req.factor_weights else "",
        filter_conditions_json=json.dumps(req.filter_conditions) if req.filter_conditions else "",
        universe=req.universe,
        date=req.date,
        selector=services.stock_selector,
    )
    return result
