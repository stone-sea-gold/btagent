"""Strategy persistence, version-chain and comparison adapters."""

from __future__ import annotations

import json

from src.agent.adapters._util import to_json
from src.agent.deps import AgentDeps
from src.agent.registry import ToolRegistry
from src.tools.storage_tools import (
    delete_strategy,
    list_strategies,
    load_strategy,
    save_strategy,
    search_strategies,
)
from src.tools.comparison_tools import compare_strategies, update_strategy

DOMAIN = "storage"


def register(registry: ToolRegistry, deps: AgentDeps) -> None:
    """Register strategy-storage tools."""
    store = deps.strategy_store

    @registry.tool(DOMAIN)
    def _save_strategy(
        name: str, config_json: str, description: str = "",
        agent_summary: str = "", version: int = 1, parent_id: str = "",
    ) -> str:
        """Save a strategy to persistent storage with version chain."""
        config = json.loads(config_json)
        result = save_strategy(
            name, config, store, description,
            agent_summary=agent_summary, version=version,
            parent_id=parent_id or None,
        )
        return to_json(result)

    @registry.tool(DOMAIN)
    def _load_strategy(strategy_id: str) -> str:
        """Load a saved strategy by ID."""
        return to_json(load_strategy(strategy_id, store))

    @registry.tool(DOMAIN)
    def _list_strategies() -> str:
        """List all saved strategies."""
        return to_json(list_strategies(store))

    @registry.tool(DOMAIN)
    def _search_strategies(query: str) -> str:
        """Search strategies by semantic similarity."""
        return to_json(search_strategies(query, store))

    @registry.tool(DOMAIN)
    def _delete_strategy(strategy_id: str) -> str:
        """Delete a strategy by ID."""
        return to_json(delete_strategy(strategy_id, store))

    @registry.tool(DOMAIN)
    def _compare_strategies(strategy_ids: str) -> str:
        """Compare multiple strategies side-by-side."""
        ids = [s.strip() for s in strategy_ids.split(",") if s.strip()]
        return to_json(compare_strategies(ids, store))

    @registry.tool(DOMAIN)
    def _update_strategy(
        strategy_id: str, modifications_json: str, agent_summary: str = ""
    ) -> str:
        """Update a strategy by creating a new version."""
        modifications = json.loads(modifications_json)
        result = update_strategy(strategy_id, modifications, store, agent_summary)
        return to_json(result)

    @registry.tool(DOMAIN)
    def _get_version_chain(strategy_id: str) -> str:
        """Get the full version chain for a strategy."""
        return to_json(store.get_version_chain(strategy_id))


__all__ = ["register", "DOMAIN"]
