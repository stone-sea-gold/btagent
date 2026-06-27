"""Factor API routes."""

from fastapi import APIRouter

from src.api.dependencies import get_services
from src.api.schemas import FactorCreateRequest, FactorSearchRequest
from src.tools.factor_tools import create_factor, search_factors

router = APIRouter()


@router.get("/search")
async def search_factors_endpoint(q: str, limit: int = 5):
    """Search factors by natural language query."""
    services = get_services()
    results = search_factors(q, services.factor_store, limit=limit)
    return {"factors": results, "count": len(results)}


@router.post("/")
async def create_factor_endpoint(req: FactorCreateRequest):
    """Create a new custom factor."""
    services = get_services()
    result = create_factor(
        id=req.id,
        name=req.name,
        description=req.description,
        category=req.category,
        formula=req.formula,
        factor_store=services.factor_store,
        tags=req.tags,
    )
    return result


@router.get("/")
async def list_factors_endpoint(category: str = "", limit: int = 100):
    """List all factors, optionally filtered by category."""
    services = get_services()
    if category:
        from src.core.models import FactorCategory
        factors = services.factor_store.list_by_category(FactorCategory(category))
    else:
        factors = services.factor_store.list_all()
    return {
        "factors": [
            {
                "id": f.id,
                "name": f.name,
                "description": f.description,
                "category": f.category.value,
                "tags": f.tags,
                "source": f.parameters.get("source", "unknown"),
            }
            for f in factors[:limit]
        ],
        "count": len(factors),
    }
