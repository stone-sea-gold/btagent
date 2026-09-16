"""Trading-calendar and data-coverage adapters.

These pass their result straight through: the underlying functions already
return model-ready JSON strings.
"""

from __future__ import annotations

from src.agent.deps import AgentDeps
from src.agent.registry import ToolRegistry
from src.tools.calendar_tools import (
    get_current_date,
    get_trading_days,
    resolve_relative_date,
)
from src.tools.data_tools import check_data_coverage

DOMAIN = "calendar"


def register(registry: ToolRegistry, deps: AgentDeps) -> None:
    """Register calendar-domain tools."""

    @registry.tool(DOMAIN)
    def _get_current_date() -> str:
        """Get today's date and the latest trading day."""
        return get_current_date()

    @registry.tool(DOMAIN)
    def _resolve_relative_date(expression: str, reference_date: str = "") -> str:
        """Resolve a relative date expression to absolute date(s)."""
        return resolve_relative_date(expression, reference_date)

    @registry.tool(DOMAIN)
    def _get_trading_days(start_date: str, end_date: str) -> str:
        """Get all trading days in a date range."""
        return get_trading_days(start_date, end_date)

    @registry.tool(DOMAIN)
    def _check_data_coverage() -> str:
        """Check Qlib data coverage and freshness."""
        return check_data_coverage()


__all__ = ["register", "DOMAIN"]
