"""A-share capital-flow and market-signal adapters."""

from __future__ import annotations

from src.agent.adapters._util import to_json
from src.agent.deps import AgentDeps
from src.agent.registry import ToolRegistry
from src.tools.astock_signal import (
    fetch_block_trade,
    fetch_concept_blocks,
    fetch_daily_dragon_tiger,
    fetch_dividend_history,
    fetch_dragon_tiger,
    fetch_fund_flow,
    fetch_fund_flow_120d,
    fetch_holder_change,
    fetch_industry_ranking,
    fetch_lockup_expiry,
    fetch_margin_trading,
    fetch_northbound_flow,
)

DOMAIN = "signal"


def register(registry: ToolRegistry, deps: AgentDeps) -> None:
    """Register signal-domain tools."""

    @registry.tool(DOMAIN)
    def _fetch_northbound_flow() -> str:
        """获取北向资金实时流向（沪股通/深股通）"""
        return to_json(fetch_northbound_flow())

    @registry.tool(DOMAIN)
    def _fetch_concept_blocks(code: str) -> str:
        """获取个股所属板块概念（行业/概念/地域）"""
        return to_json(fetch_concept_blocks(code))

    @registry.tool(DOMAIN)
    def _fetch_fund_flow(code: str) -> str:
        """获取个股资金流向（主力/大单/中单/小单，分钟级）"""
        return to_json(fetch_fund_flow(code))

    @registry.tool(DOMAIN)
    def _fetch_fund_flow_120d(code: str) -> str:
        """获取个股120日资金流向（日级）"""
        return to_json(fetch_fund_flow_120d(code))

    @registry.tool(DOMAIN)
    def _fetch_dragon_tiger(code: str, trade_date: str = "") -> str:
        """获取个股龙虎榜席位数据"""
        return to_json(fetch_dragon_tiger(code, trade_date))

    @registry.tool(DOMAIN)
    def _fetch_daily_dragon_tiger(trade_date: str = "") -> str:
        """获取全市场龙虎榜数据"""
        return to_json(fetch_daily_dragon_tiger(trade_date))

    @registry.tool(DOMAIN)
    def _fetch_lockup_expiry(code: str, forward_days: int = 90) -> str:
        """获取限售解禁预警（未来90天）"""
        return to_json(fetch_lockup_expiry(code, forward_days))

    @registry.tool(DOMAIN)
    def _fetch_industry_ranking(top_n: int = 20) -> str:
        """获取行业涨跌排名"""
        return to_json(fetch_industry_ranking(top_n))

    @registry.tool(DOMAIN)
    def _fetch_margin_trading(code: str, page_size: int = 30) -> str:
        """获取融资融券数据"""
        return to_json(fetch_margin_trading(code, page_size))

    @registry.tool(DOMAIN)
    def _fetch_block_trade(code: str, page_size: int = 20) -> str:
        """获取大宗交易数据"""
        return to_json(fetch_block_trade(code, page_size))

    @registry.tool(DOMAIN)
    def _fetch_holder_change(code: str, page_size: int = 10) -> str:
        """获取股东户数变化（筹码集中度）"""
        return to_json(fetch_holder_change(code, page_size))

    @registry.tool(DOMAIN)
    def _fetch_dividend_history(code: str, page_size: int = 20) -> str:
        """获取分红送转历史"""
        return to_json(fetch_dividend_history(code, page_size))


__all__ = ["register", "DOMAIN"]
