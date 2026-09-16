"""Parameter-optimisation adapter."""

from __future__ import annotations

from src.agent.adapters._util import to_json
from src.agent.deps import AgentDeps
from src.agent.registry import ToolRegistry
from src.tools.optimize_tools import optimize_parameters

DOMAIN = "optimize"


def register(registry: ToolRegistry, deps: AgentDeps) -> None:
    """Register optimisation-domain tools."""

    @registry.tool(DOMAIN)
    def _optimize_parameters(
        strategy_id: str, method: str = "bayesian",
        param_ranges_json: str = "", metric: str = "sharpe_ratio",
        n_trials: int = 50, start_date: str = "", end_date: str = "",
    ) -> str:
        """Run parameter optimization."""
        result = optimize_parameters(
            strategy_id=strategy_id, method=method,
            param_ranges_json=param_ranges_json, metric=metric,
            n_trials=n_trials, start_date=start_date, end_date=end_date,
            optimizer=deps.param_optimizer,
        )
        return to_json(result)


__all__ = ["register", "DOMAIN"]
