"""Stop-loss rule adapters."""

from __future__ import annotations

from src.agent.adapters._util import to_json
from src.agent.deps import AgentDeps
from src.agent.registry import ToolRegistry
from src.tools.stoploss_tools import (
    add_stoploss_rules,
    check_stoploss_scenarios,
    run_backtest_with_stoploss,
)

DOMAIN = "stoploss"


def register(registry: ToolRegistry, deps: AgentDeps) -> None:
    """Register stop-loss-domain tools."""

    @registry.tool(DOMAIN)
    def _add_stoploss_rules(strategy_config_json: str, rules_json: str) -> str:
        """Add stop-loss rules to a strategy config."""
        return to_json(add_stoploss_rules(strategy_config_json, rules_json))

    @registry.tool(DOMAIN)
    def _run_backtest_with_stoploss(
        strategy_config_json: str, stoploss_rules_json: str
    ) -> str:
        """Run backtest with stop-loss rules."""
        result = run_backtest_with_stoploss(
            strategy_config_json, stoploss_rules_json,
            compiler=deps.strategy_compiler, engine=deps.backtest_engine,
        )
        return to_json(result)

    @registry.tool(DOMAIN)
    def _check_stoploss_scenarios(
        strategy_config_json: str, stoploss_rules_json: str
    ) -> str:
        """Analyze stop-loss trigger scenarios."""
        result = check_stoploss_scenarios(
            strategy_config_json, stoploss_rules_json,
            compiler=deps.strategy_compiler, engine=deps.backtest_engine,
        )
        return to_json(result)


__all__ = ["register", "DOMAIN"]
