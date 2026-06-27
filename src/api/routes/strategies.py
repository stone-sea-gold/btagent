"""Strategy API routes."""

from fastapi import APIRouter

from src.api.dependencies import get_services
from src.api.schemas import (
    StrategyCompareRequest,
    StrategySaveRequest,
    StrategyUpdateRequest,
)
from src.tools.comparison_tools import compare_strategies, update_strategy
from src.tools.storage_tools import (
    list_strategies,
    load_strategy,
    save_strategy,
    search_strategies,
)

router = APIRouter()


@router.get("/")
async def list_strategies_endpoint(limit: int = 20):
    """List all saved strategies."""
    services = get_services()
    result = list_strategies(services.strategy_store, limit=limit)
    return {"strategies": result, "count": len(result)}


@router.get("/search")
async def search_strategies_endpoint(q: str, limit: int = 5):
    """Search strategies by semantic similarity."""
    services = get_services()
    result = search_strategies(q, services.strategy_store, limit=limit)
    return {"strategies": result, "count": len(result)}


@router.get("/{strategy_id}")
async def get_strategy_endpoint(strategy_id: str):
    """Load a strategy by ID."""
    services = get_services()
    result = load_strategy(strategy_id, services.strategy_store)
    return result


@router.get("/{strategy_id}/versions")
async def get_version_chain_endpoint(strategy_id: str):
    """Get the version chain for a strategy."""
    services = get_services()
    chain = services.strategy_store.get_version_chain(strategy_id)
    return {"versions": chain, "count": len(chain)}


@router.post("/")
async def save_strategy_endpoint(req: StrategySaveRequest):
    """Save a strategy."""
    services = get_services()
    result = save_strategy(
        name=req.name,
        config=req.config,
        store=services.strategy_store,
        description=req.description,
        agent_summary=req.agent_summary,
        version=req.version,
        parent_id=req.parent_id,
    )
    return result


@router.put("/{strategy_id}")
async def update_strategy_endpoint(strategy_id: str, req: StrategyUpdateRequest):
    """Update a strategy (creates new version)."""
    services = get_services()
    result = update_strategy(
        strategy_id=strategy_id,
        modifications=req.modifications,
        store=services.strategy_store,
        agent_summary=req.agent_summary,
    )
    return result


@router.post("/compare")
async def compare_strategies_endpoint(req: StrategyCompareRequest):
    """Compare multiple strategies."""
    services = get_services()
    result = compare_strategies(req.strategy_ids, services.strategy_store)
    return result
