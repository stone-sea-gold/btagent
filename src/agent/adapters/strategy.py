"""Strategy composition adapter."""

from __future__ import annotations

from src.agent.adapters._util import to_json
from src.agent.deps import AgentDeps
from src.agent.registry import ToolRegistry
from src.exceptions import FactorNotFoundError
from src.tools.strategy_tools import compose_strategy

DOMAIN = "strategy"


def register(registry: ToolRegistry, deps: AgentDeps) -> None:
    """Register strategy-domain tools."""

    @registry.tool(DOMAIN)
    def _compose_strategy(
        name: str, factor_ids: str, start_date: str, end_date: str,
        selection_rule: str = "top_k", max_holding: int = 10,
        rebalance_freq: str = "monthly", weight_scheme: str = "equal",
    ) -> str:
        """Compose a strategy from factors. Validates factor IDs exist."""
        fid_list = [f.strip() for f in factor_ids.split(",") if f.strip()]

        # Validate before composing: an unknown factor ID produces a Qlib error
        # deep in the compiler, which is far less actionable for the model than
        # a list of the IDs that actually exist.
        invalid_ids = []
        for fid in fid_list:
            try:
                deps.factor_store.get(fid)
            except FactorNotFoundError:
                invalid_ids.append(fid)

        if invalid_ids:
            available = [f.id for f in deps.factor_store.list_all()]
            return to_json({
                "error": f"因子 ID 不存在: {invalid_ids}",
                "available_factor_ids": available,
                "hint": "请使用 search_factors 搜索正确的因子 ID",
                "status": "invalid_factor_ids",
            })

        result = compose_strategy(
            name=name, factor_ids=fid_list,
            start_date=start_date, end_date=end_date,
            selection_rule=selection_rule, max_holding=max_holding,
            rebalance_freq=rebalance_freq, weight_scheme=weight_scheme,
        )
        return to_json(result)


__all__ = ["register", "DOMAIN"]
