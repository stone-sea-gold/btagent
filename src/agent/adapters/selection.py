"""Stock selection pipeline adapter."""

from __future__ import annotations

from src.agent.adapters._util import to_json
from src.agent.deps import AgentDeps
from src.agent.registry import ToolRegistry
from src.tools.selection_tools import select_stocks

DOMAIN = "selection"


def register(registry: ToolRegistry, deps: AgentDeps) -> None:
    """Register selection-domain tools."""

    @registry.tool(DOMAIN)
    def _select_stocks(
        name: str, factor_ids: str, top_k: int = 50,
        factor_weights_json: str = "", filter_conditions_json: str = "",
        universe: str = "csi300", date: str = "",
    ) -> str:
        """Run stock selection pipeline."""
        result = select_stocks(
            name=name, factor_ids=factor_ids, top_k=top_k,
            factor_weights_json=factor_weights_json,
            filter_conditions_json=filter_conditions_json,
            universe=universe, date=date, selector=deps.stock_selector,
        )
        return to_json(result)


__all__ = ["register", "DOMAIN"]
