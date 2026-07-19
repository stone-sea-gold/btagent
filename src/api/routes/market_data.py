"""Market data API routes — pytdx + baostock."""

from fastapi import APIRouter, Query

from src.tools.market_data_tools import (
    fetch_financial_summary,
    fetch_index_constituents,
    fetch_industry_stocks,
    fetch_quarterly_financials,
    fetch_sector_flow,
    fetch_stock_hist,
    fetch_stock_quote,
)

router = APIRouter()


@router.get("/quote")
async def get_stock_quote(symbol: str = Query(..., min_length=1, description="股票代码")):
    """获取个股实时行情"""
    return fetch_stock_quote(symbol)


@router.get("/history")
async def get_stock_history(
    symbol: str = Query(..., min_length=1),
    start: str = Query("", description="起始日期 YYYYMMDD"),
    end: str = Query("", description="截止日期 YYYYMMDD"),
    period: str = Query("daily", description="周期: daily/weekly/monthly"),
    adjust: str = Query("qfq", description="复权: qfq/hfq/空"),
):
    """获取历史 K 线数据"""
    return fetch_stock_hist(symbol, start, end, period, adjust)


@router.get("/financial")
async def get_financial_summary(symbol: str = Query(..., min_length=1)):
    """获取个股基本面摘要"""
    return fetch_financial_summary(symbol)


@router.get("/sector-flow")
async def get_sector_flow():
    """获取行业板块列表"""
    return fetch_sector_flow()


@router.get("/quarterly")
async def get_quarterly_financials(
    symbol: str = Query(..., min_length=1),
    year: int = Query(0, description="年份"),
    quarter: int = Query(0, description="季度 1-4"),
):
    """获取季度财务指标"""
    return fetch_quarterly_financials(symbol, year, quarter)


@router.get("/industry")
async def get_industry_stocks(industry: str = Query(..., min_length=1)):
    """按行业获取股票列表"""
    return fetch_industry_stocks(industry)


@router.get("/index-constituents")
async def get_index_constituents(index: str = Query("csi300")):
    """获取指数成分股列表"""
    return fetch_index_constituents(index)
