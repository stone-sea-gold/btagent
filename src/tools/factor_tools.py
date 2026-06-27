"""Factor-related tools for the Agent."""

from src.core.factor_store import FactorStore
from src.core.models import FactorCreate, FactorSearchResult
from src.exceptions import FactorDuplicateError, FactorNotFoundError
from src.logging import get_logger

logger = get_logger("factor_tools")


def search_factors(query: str, factor_store: FactorStore, limit: int = 5) -> list[dict]:
    """Search factors by natural language query.

    Args:
        query: Natural language search query (e.g., "动量因子", "价值指标")
        factor_store: FactorStore instance.
        limit: Max results to return.

    Returns:
        List of factor dicts with relevance scores.
    """
    results = factor_store.search(query, limit=limit)
    logger.info("search_factors", query=query, result_count=len(results))
    return [
        {
            "id": r.factor.id,
            "name": r.factor.name,
            "description": r.factor.description,
            "category": r.factor.category.value,
            "score": round(r.score, 3),
            "tags": r.factor.tags,
        }
        for r in results
    ]


def create_factor(
    id: str,
    name: str,
    description: str,
    category: str,
    formula: str,
    factor_store: FactorStore,
    tags: list[str] | None = None,
    parameters: dict | None = None,
) -> dict:
    """Create a new custom factor.

    Args:
        id: Unique factor ID (lowercase, underscores, e.g., "my_factor")
        name: Human-readable name
        description: What the factor measures
        category: One of momentum, value, quality, volatility, size, liquidity, growth, technical
        formula: Qlib expression (e.g., "Ref($close, 0) / Ref($close, 60) - 1")
        factor_store: FactorStore instance.
        tags: Searchable tags.
        parameters: Configurable parameters.

    Returns:
        Created factor dict.
    """
    try:
        factor_input = FactorCreate(
            id=id,
            name=name,
            description=description,
            category=category,
            formula=formula,
            tags=tags or [],
            parameters=parameters or {},
        )
        factor = factor_store.create(factor_input)
        logger.info("create_factor", factor_id=factor.id, category=factor.category.value)
        return {
            "id": factor.id,
            "name": factor.name,
            "description": factor.description,
            "category": factor.category.value,
            "formula": factor.formula,
            "tags": factor.tags,
            "status": "created",
        }
    except FactorDuplicateError as e:
        logger.warning("create_factor_duplicate", factor_id=id)
        return {"error": str(e), "status": "duplicate"}
    except Exception as e:
        logger.error("create_factor_error", factor_id=id, error=str(e))
        return {"error": str(e), "status": "error"}
