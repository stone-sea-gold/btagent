"""News, announcement and popularity-ranking adapters."""

from __future__ import annotations

from src.agent.adapters._util import to_json
from src.agent.deps import AgentDeps
from src.agent.registry import ToolRegistry
from src.tools.astock_news import (
    fetch_announcements,
    fetch_global_news,
    fetch_hot_concept,
    fetch_hot_list,
    fetch_hot_rank,
    fetch_market_telegraph,
    fetch_stock_news,
)

DOMAIN = "news"


def register(registry: ToolRegistry, deps: AgentDeps) -> None:
    """Register news-domain tools."""

    @registry.tool(DOMAIN)
    def _fetch_stock_news(code: str, page_size: int = 20) -> str:
        """获取个股新闻"""
        return to_json(fetch_stock_news(code, page_size))

    @registry.tool(DOMAIN)
    def _fetch_market_telegraph(page_size: int = 50) -> str:
        """获取财联社全市场快讯"""
        return to_json(fetch_market_telegraph(page_size))

    @registry.tool(DOMAIN)
    def _fetch_global_news(page_size: int = 50) -> str:
        """获取东财全球财经资讯"""
        return to_json(fetch_global_news(page_size))

    @registry.tool(DOMAIN)
    def _fetch_announcements(code: str, page_size: int = 20) -> str:
        """获取公司公告（巨潮源）"""
        return to_json(fetch_announcements(code, page_size))

    @registry.tool(DOMAIN)
    def _fetch_hot_list(period: str = "hour") -> str:
        """获取同花顺热榜"""
        return to_json(fetch_hot_list(period))

    @registry.tool(DOMAIN)
    def _fetch_hot_rank(top: int = 50) -> str:
        """获取东财人气榜"""
        return to_json(fetch_hot_rank(top))

    @registry.tool(DOMAIN)
    def _fetch_hot_concept(code: str) -> str:
        """获取个股概念命中"""
        return to_json(fetch_hot_concept(code))


__all__ = ["register", "DOMAIN"]
