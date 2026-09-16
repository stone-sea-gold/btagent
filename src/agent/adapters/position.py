"""Portfolio and position-management adapters."""

from __future__ import annotations

from src.agent.adapters._util import to_json
from src.agent.deps import AgentDeps
from src.agent.registry import ToolRegistry
from src.tools.position_tools import (
    get_portfolio_status,
    save_holdings,
    save_position_rules,
)

DOMAIN = "position"


def register(registry: ToolRegistry, deps: AgentDeps) -> None:
    """Register position-domain tools."""

    @registry.tool(DOMAIN)
    def _save_holdings(session_id: str, holdings_json: str) -> str:
        """Save portfolio holdings."""
        return to_json(save_holdings(session_id, holdings_json, deps.position_manager))

    @registry.tool(DOMAIN)
    def _get_portfolio_status(session_id: str) -> str:
        """Get portfolio status and check rule violations."""
        return to_json(get_portfolio_status(session_id, deps.position_manager))

    @registry.tool(DOMAIN)
    def _save_position_rules(session_id: str, rules_json: str) -> str:
        """Save position management rules."""
        return to_json(
            save_position_rules(session_id, rules_json, deps.position_manager)
        )


__all__ = ["register", "DOMAIN"]
