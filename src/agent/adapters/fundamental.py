"""Research-report and valuation adapters."""

from __future__ import annotations

from src.agent.adapters._util import to_json
from src.agent.deps import AgentDeps
from src.agent.registry import ToolRegistry
from src.tools.astock_fundamental import (
    fetch_eps_forecast,
    fetch_industry_reports,
    fetch_stock_reports,
    fetch_valuation,
)

DOMAIN = "fundamental"


def register(registry: ToolRegistry, deps: AgentDeps) -> None:
    """Register fundamental-domain tools."""

    @registry.tool(DOMAIN)
    def _fetch_stock_reports(code: str, max_pages: int = 3) -> str:
        """获取个股研报列表（评级、目标价、机构）"""
        return to_json(fetch_stock_reports(code, max_pages))

    @registry.tool(DOMAIN)
    def _fetch_industry_reports(industry_code: str = "*", max_pages: int = 3) -> str:
        """获取行业研报列表"""
        return to_json(fetch_industry_reports(industry_code, max_pages))

    @registry.tool(DOMAIN)
    def _fetch_eps_forecast(code: str) -> str:
        """获取机构一致预期EPS"""
        return to_json(fetch_eps_forecast(code))

    @registry.tool(DOMAIN)
    def _fetch_valuation(code: str) -> str:
        """获取完整估值分析（PE/PEG/消化时间）"""
        return to_json(fetch_valuation(code))


__all__ = ["register", "DOMAIN"]
