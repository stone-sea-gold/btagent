"""Factor library adapters (search, create)."""

from __future__ import annotations

from src.agent.adapters._util import to_json
from src.agent.deps import AgentDeps
from src.agent.registry import ToolRegistry
from src.tools.factor_tools import create_factor, search_factors

DOMAIN = "factor"


def register(registry: ToolRegistry, deps: AgentDeps) -> None:
    """Register factor-domain tools."""

    @registry.tool(DOMAIN)
    def _search_factors(query: str) -> str:
        """Search the factor library by natural language query."""
        return to_json(search_factors(query, deps.factor_store))

    @registry.tool(DOMAIN)
    def _create_factor(
        id: str, name: str, description: str, category: str, formula: str,
        tags: str = "",
    ) -> str:
        """Create a new custom factor."""
        tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []
        result = create_factor(
            id=id, name=name, description=description,
            category=category, formula=formula,
            factor_store=deps.factor_store, tags=tag_list,
        )
        return to_json(result)


__all__ = ["register", "DOMAIN"]
