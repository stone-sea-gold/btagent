"""Market-quote and financial-summary adapters."""

from __future__ import annotations

from src.agent.adapters._util import to_json
from src.agent.deps import AgentDeps
from src.agent.registry import ToolRegistry
from src.tools.market_data_tools import (
    fetch_financial_summary,
    fetch_index_constituents,
    fetch_industry_stocks,
    fetch_quarterly_financials,
    fetch_sector_flow,
    fetch_stock_hist,
    fetch_stock_quote,
)

DOMAIN = "market_data"


def register(registry: ToolRegistry, deps: AgentDeps) -> None:
    """Register market-data-domain tools."""

    @registry.tool(DOMAIN)
    def _fetch_stock_quote(symbol: str) -> str:
        """获取个股实时行情（最新价、涨跌幅、成交量、换手率）"""
        return to_json(fetch_stock_quote(symbol))

    @registry.tool(DOMAIN)
    def _fetch_stock_hist(
        symbol: str, start: str = "", end: str = "",
        period: str = "daily", adjust: str = "qfq",
    ) -> str:
        """获取历史 K 线数据（日/周/月线，前复权/后复权）"""
        return to_json(fetch_stock_hist(symbol, start, end, period, adjust))

    @registry.tool(DOMAIN)
    def _fetch_financial_summary(symbol: str) -> str:
        """获取个股基本面摘要（PE、PB、ROE、市值等）"""
        return to_json(fetch_financial_summary(symbol))

    @registry.tool(DOMAIN)
    def _fetch_sector_flow() -> str:
        """获取行业板块列表"""
        return to_json(fetch_sector_flow())

    @registry.tool(DOMAIN)
    def _fetch_quarterly_financials(symbol: str, year: int = 0, quarter: int = 0) -> str:
        """获取季度财务指标（ROE/净利润率/毛利率等）"""
        return to_json(fetch_quarterly_financials(symbol, year, quarter))

    @registry.tool(DOMAIN)
    def _fetch_industry_stocks(industry: str) -> str:
        """按行业获取股票列表"""
        return to_json(fetch_industry_stocks(industry))

    @registry.tool(DOMAIN)
    def _fetch_index_constituents(index: str = "csi300") -> str:
        """获取指数成分股列表（沪深300/中证500等）"""
        return to_json(fetch_index_constituents(index))


__all__ = ["register", "DOMAIN"]
