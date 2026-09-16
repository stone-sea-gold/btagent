"""Backtest execution and analysis adapters."""

from __future__ import annotations

import json

from src.agent.adapters._util import to_json
from src.agent.deps import AgentDeps
from src.agent.registry import ToolRegistry
from src.tools.backtest_tools import analyze_backtest, run_backtest

DOMAIN = "backtest"


def register(registry: ToolRegistry, deps: AgentDeps) -> None:
    """Register backtest-domain tools."""

    @registry.tool(DOMAIN)
    def _run_backtest(strategy_config_json: str) -> str:
        """Run a backtest with the given strategy config JSON."""
        config = json.loads(strategy_config_json)
        result = run_backtest(config, deps.strategy_compiler, deps.backtest_engine)
        return to_json(result)

    @registry.tool(DOMAIN)
    def _analyze_backtest(backtest_result_json: str) -> str:
        """Analyze backtest results and generate natural language summary."""
        result = json.loads(backtest_result_json)
        # Already returns model-ready prose, so no JSON wrapping here.
        return analyze_backtest(result)


__all__ = ["register", "DOMAIN"]
