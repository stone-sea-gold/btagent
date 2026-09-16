"""A-share signal & capital flow tools — northbound, dragon tiger, fund flow.

Data sources:
- 东财 (EastMoney): capital flow, dragon tiger, margin trading, block trade
- 同花顺 (THS): northbound flow, concept blocks

All interfaces are free, no API key required.
"""

import json
import time
import random
from datetime import datetime, timedelta

import requests
import pandas as pd

from src.logging import get_logger

logger = get_logger("astock_signal")

# ── Constants & Session ─────────────────────────────────────────

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
DATACENTER_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"

# EastMoney session with rate limiting
EM_SESSION = requests.Session()
EM_SESSION.headers.update({"User-Agent": UA})
_em_last_call = [0.0]
EM_MIN_INTERVAL = 1.0


def _em_get(url: str, params: dict | None = None, headers: dict | None = None,
            timeout: int = 15, **kwargs):
    """EastMoney unified request: auto-throttle + session reuse."""
    wait = EM_MIN_INTERVAL - (time.time() - _em_last_call[0])
    if wait > 0:
        time.sleep(wait + random.uniform(0.1, 0.5))
    try:
        return EM_SESSION.get(url, params=params, headers=headers, timeout=timeout, **kwargs)
    finally:
        _em_last_call[0] = time.time()


def _normalize_code(code: str) -> str:
    """Normalize stock code to 6 digits."""
    code = code.strip().upper()
    for prefix in ["SH", "SZ", "BJ"]:
        code = code.replace(prefix, "")
    return code.replace(".SH", "").replace(".SZ", "").replace(".BJ", "")


def _get_prefix(code: str) -> str:
    """Get market prefix from code."""
    if code.startswith(("6", "9")):
        return "sh"
    elif code.startswith("8"):
        return "bj"
    else:
        return "sz"


def _eastmoney_datacenter(report_name: str, columns: str = "ALL",
                          filter_str: str = "", sort_columns: str = "",
                          sort_types: int = -1, page_size: int = 50,
                          page_number: int = 1) -> dict:
    """EastMoney datacenter unified query."""
    params = {
        "reportName": report_name,
        "columns": columns,
        "filter": filter_str,
        "sortColumns": sort_columns,
        "sortTypes": sort_types,
        "pageSize": page_size,
        "pageNumber": page_number,
        "source": "WEB",
        "client": "WEB",
    }
    r = _em_get(DATACENTER_URL, params=params, timeout=15)
    return r.json()


# ── Northbound Flow ─────────────────────────────────────────────


def fetch_northbound_flow() -> dict:
    """获取北向资金实时流向（同花顺源）。

    Returns:
        {hgt_net, sgt_net, total_net, hgt_buy, hgt_sell, status}
    """
    try:
        url = "https://basic.10jqka.com.cn/api/hgt/hgtflow"
        headers = {"User-Agent": UA, "Referer": "https://basic.10jqka.com.cn/"}
        r = requests.get(url, headers=headers, timeout=15)
        data = r.json()

        if data.get("status_code") != 0:
            return {"error": "获取北向资金失败", "status": "error"}

        result = data.get("data", {})
        hgt = result.get("hgt", {})
        sgt = result.get("sgt", {})

        return {
            "hgt_net": float(hgt.get("net", 0)),  # 沪股通净流入（万元）
            "sgt_net": float(sgt.get("net", 0)),  # 深股通净流入（万元）
            "total_net": float(hgt.get("net", 0)) + float(sgt.get("net", 0)),
            "hgt_buy": float(hgt.get("buy", 0)),
            "hgt_sell": float(hgt.get("sell", 0)),
            "sgt_buy": float(sgt.get("buy", 0)),
            "sgt_sell": float(sgt.get("sell", 0)),
            "update_time": result.get("time", ""),
            "status": "success",
        }
    except Exception as e:
        logger.error("northbound_flow_error", error=str(e))
        return {"error": f"获取北向资金失败: {e}", "status": "error"}


# ── Concept Blocks ──────────────────────────────────────────────


def fetch_concept_blocks(code: str) -> dict:
    """获取个股所属板块概念（行业/概念/地域）。

    Args:
        code: 股票代码

    Returns:
        {code, blocks: [{name, type, change_pct, leader}], status}
    """
    try:
        code = _normalize_code(code)

        url = "https://push2.eastmoney.com/api/qt/slist/get"
        params = {
            "spt": "3",
            "fields": "f12,f14,f3,f128,f136,f140",
            "secid": f"{'1' if code.startswith('6') else '0'}.{code}",
        }
        r = _em_get(url, params=params, timeout=15)
        data = r.json()

        blocks = []
        for item in data.get("data", {}).get("diff", []):
            blocks.append({
                "code": item.get("f12", ""),
                "name": item.get("f14", ""),
                "change_pct": item.get("f3", 0) / 100 if item.get("f3") else 0,
                "leader": item.get("f140", ""),
                "leader_change": item.get("f136", 0) / 100 if item.get("f136") else 0,
            })

        return {
            "code": code,
            "blocks": blocks,
            "count": len(blocks),
            "status": "success",
        }
    except Exception as e:
        logger.error("concept_blocks_error", code=code, error=str(e))
        return {"error": f"获取板块概念失败: {e}", "status": "error"}


# ── Fund Flow ───────────────────────────────────────────────────


def fetch_fund_flow(code: str) -> dict:
    """获取个股资金流向（分钟级，主力/大单/中单/小单）。

    Args:
        code: 股票代码

    Returns:
        {code, flows: [{time, main_in, main_out, super_in, super_out, ...}], status}
    """
    try:
        code = _normalize_code(code)
        market = "1" if code.startswith("6") else "0"

        url = "https://push2.eastmoney.com/api/qt/stock/fflow/kline/get"
        params = {
            "secid": f"{market}.{code}",
            "fields1": "f1,f2,f3,f7",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65",
            "klt": "1",
            "lmt": "120",
        }
        r = _em_get(url, params=params, timeout=15)
        data = r.json()

        flows = []
        for line in data.get("data", {}).get("klines", []):
            parts = line.split(",")
            if len(parts) >= 7:
                flows.append({
                    "time": parts[0],
                    "main_net": float(parts[1]),  # 主力净流入
                    "super_net": float(parts[2]),  # 超大单净流入
                    "big_net": float(parts[3]),  # 大单净流入
                    "mid_net": float(parts[4]),  # 中单净流入
                    "small_net": float(parts[5]),  # 小单净流入
                })

        return {
            "code": code,
            "flows": flows,
            "count": len(flows),
            "status": "success",
        }
    except Exception as e:
        logger.error("fund_flow_error", code=code, error=str(e))
        return {"error": f"获取资金流向失败: {e}", "status": "error"}


def fetch_fund_flow_120d(code: str) -> dict:
    """获取个股120日资金流向（日级）。

    Args:
        code: 股票代码

    Returns:
        {code, flows: [{date, main_net, super_net, big_net, mid_net, small_net}], status}
    """
    try:
        code = _normalize_code(code)
        market = "1" if code.startswith("6") else "0"

        url = "https://push2.eastmoney.com/api/qt/stock/fflow/daykline/get"
        params = {
            "secid": f"{market}.{code}",
            "fields1": "f1,f2,f3,f7",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65",
            "lmt": "120",
        }
        r = _em_get(url, params=params, timeout=15)
        data = r.json()

        flows = []
        for line in data.get("data", {}).get("klines", []):
            parts = line.split(",")
            if len(parts) >= 7:
                flows.append({
                    "date": parts[0],
                    "main_net": float(parts[1]),
                    "super_net": float(parts[2]),
                    "big_net": float(parts[3]),
                    "mid_net": float(parts[4]),
                    "small_net": float(parts[5]),
                })

        return {
            "code": code,
            "flows": flows,
            "count": len(flows),
            "status": "success",
        }
    except Exception as e:
        logger.error("fund_flow_120d_error", code=code, error=str(e))
        return {"error": f"获取120日资金流失败: {e}", "status": "error"}


# ── Dragon Tiger Board ──────────────────────────────────────────


def fetch_dragon_tiger(code: str, trade_date: str = "") -> dict:
    """获取个股龙虎榜席位数据。

    Args:
        code: 股票代码
        trade_date: 交易日期（YYYY-MM-DD），默认最近

    Returns:
        {code, date, buy_seats: [{name, buy, sell}], sell_seats: [...], status}
    """
    try:
        code = _normalize_code(code)
        if not trade_date:
            trade_date = datetime.now().strftime("%Y-%m-%d")

        # Convert date format
        date_str = trade_date.replace("-", "")

        filter_str = f'(TRADE_DATE=\'{trade_date}\')(SECURITY_CODE="{code}")'
        result = _eastmoney_datacenter(
            report_name="RPT_DAILYBILLBOARD_DETAILSNEW",
            columns="ALL",
            filter_str=filter_str,
            sort_columns="BUY_AMT",
            sort_types=-1,
            page_size=50,
        )

        items = result.get("result", {}).get("data", [])
        if not items:
            return {"code": code, "date": trade_date, "message": "该日无龙虎榜数据", "status": "empty"}

        buy_seats = []
        sell_seats = []
        for item in items:
            seat = {
                "name": item.get("OPERATEDEPT_NAME", ""),
                "buy": item.get("BUY_AMT", 0) or 0,
                "sell": item.get("SELL_AMT", 0) or 0,
                "net": (item.get("BUY_AMT", 0) or 0) - (item.get("SELL_AMT", 0) or 0),
            }
            if seat["buy"] > seat["sell"]:
                buy_seats.append(seat)
            else:
                sell_seats.append(seat)

        return {
            "code": code,
            "date": trade_date,
            "buy_seats": sorted(buy_seats, key=lambda x: -x["net"])[:10],
            "sell_seats": sorted(sell_seats, key=lambda x: x["net"])[:10],
            "status": "success",
        }
    except Exception as e:
        logger.error("dragon_tiger_error", code=code, error=str(e))
        return {"error": f"获取龙虎榜失败: {e}", "status": "error"}


def fetch_daily_dragon_tiger(trade_date: str = "") -> dict:
    """获取全市场龙虎榜数据。

    Args:
        trade_date: 交易日期（YYYY-MM-DD），默认今天

    Returns:
        {date, stocks: [{code, name, close, change_pct, reason, net_buy}], status}
    """
    try:
        if not trade_date:
            trade_date = datetime.now().strftime("%Y-%m-%d")

        filter_str = f'(TRADE_DATE=\'{trade_date}\')'
        result = _eastmoney_datacenter(
            report_name="RPT_DAILYBILLBOARD_DETAILSNEW",
            columns="ALL",
            filter_str=filter_str,
            sort_columns="BUY_AMT",
            sort_types=-1,
            page_size=200,
        )

        items = result.get("result", {}).get("data", [])
        if not items:
            return {"date": trade_date, "message": "该日无龙虎榜数据", "status": "empty"}

        # Group by stock
        stocks = {}
        for item in items:
            code = item.get("SECURITY_CODE", "")
            if code not in stocks:
                stocks[code] = {
                    "code": code,
                    "name": item.get("SECURITY_NAME_ABBR", ""),
                    "close": item.get("CLOSE_PRICE", 0),
                    "change_pct": item.get("CHANGE_RATE", 0),
                    "reason": item.get("EXPLAIN", ""),
                    "buy_total": 0,
                    "sell_total": 0,
                }
            stocks[code]["buy_total"] += item.get("BUY_AMT", 0) or 0
            stocks[code]["sell_total"] += item.get("SELL_AMT", 0) or 0

        # Calculate net buy
        stock_list = []
        for s in stocks.values():
            s["net_buy"] = s["buy_total"] - s["sell_total"]
            stock_list.append(s)

        stock_list.sort(key=lambda x: -x["net_buy"])

        return {
            "date": trade_date,
            "stocks": stock_list[:50],
            "count": len(stock_list),
            "status": "success",
        }
    except Exception as e:
        logger.error("daily_dragon_tiger_error", error=str(e))
        return {"error": f"获取全市场龙虎榜失败: {e}", "status": "error"}


# ── Lockup Expiry ───────────────────────────────────────────────


def fetch_lockup_expiry(code: str, forward_days: int = 90) -> dict:
    """获取限售解禁预警。

    Args:
        code: 股票代码
        forward_days: 未来天数（默认90天）

    Returns:
        {code, expiries: [{date, shares, amount, type}], status}
    """
    try:
        code = _normalize_code(code)

        today = datetime.now().strftime("%Y-%m-%d")
        end_date = (datetime.now() + timedelta(days=forward_days)).strftime("%Y-%m-%d")

        filter_str = f'(SECURITY_CODE="{code}")(FREE_DATE>=\'{today}\')(FREE_DATE<=\'{end_date}\')'
        result = _eastmoney_datacenter(
            report_name="RPT_LIFT_STAGE",
            columns="ALL",
            filter_str=filter_str,
            sort_columns="FREE_DATE",
            sort_types=1,
            page_size=50,
        )

        items = result.get("result", {}).get("data", [])
        expiries = []
        for item in items:
            expiries.append({
                "date": item.get("FREE_DATE", "")[:10],
                "shares": item.get("FREE_SHARES", 0),
                "amount": item.get("FREE_CAPITAL", 0),
                "type": item.get("FREE_SHARES_TYPE", ""),
                "ratio": item.get("FREE_RATIO", 0),
            })

        return {
            "code": code,
            "expiries": expiries,
            "count": len(expiries),
            "status": "success",
        }
    except Exception as e:
        logger.error("lockup_expiry_error", code=code, error=str(e))
        return {"error": f"获取解禁预警失败: {e}", "status": "error"}


# ── Industry Comparison ─────────────────────────────────────────


def fetch_industry_ranking(top_n: int = 20) -> dict:
    """获取行业涨跌排名。

    Args:
        top_n: 返回前N个行业

    Returns:
        {industries: [{name, change_pct, up_count, down_count, leader}], status}
    """
    try:
        url = "https://push2.eastmoney.com/api/qt/clist/get"
        params = {
            "fid": "f3",
            "po": "1",
            "pz": top_n,
            "pn": "1",
            "np": "1",
            "fltt": "2",
            "invt": "2",
            "fs": "m:90+t:2",  # 行业板块
            "fields": "f2,f3,f4,f12,f14,f104,f105,f128,f140",
        }
        r = _em_get(url, params=params, timeout=15)
        data = r.json()

        industries = []
        for item in data.get("data", {}).get("diff", []):
            industries.append({
                "code": item.get("f12", ""),
                "name": item.get("f14", ""),
                "change_pct": item.get("f3", 0) / 100 if item.get("f3") else 0,
                "up_count": item.get("f104", 0),
                "down_count": item.get("f105", 0),
                "leader": item.get("f140", ""),
                "leader_change": item.get("f128", 0) / 100 if item.get("f128") else 0,
            })

        return {
            "industries": industries,
            "count": len(industries),
            "status": "success",
        }
    except Exception as e:
        logger.error("industry_ranking_error", error=str(e))
        return {"error": f"获取行业排名失败: {e}", "status": "error"}


# ── Margin Trading ──────────────────────────────────────────────


def fetch_margin_trading(code: str, page_size: int = 30) -> dict:
    """获取融资融券数据。

    Args:
        code: 股票代码
        page_size: 返回条数

    Returns:
        {code, data: [{date, margin_buy, margin_balance, short_sell, short_balance}], status}
    """
    try:
        code = _normalize_code(code)

        filter_str = f'(SCODE="{code}")'
        result = _eastmoney_datacenter(
            report_name="RPTA_WEB_RZRQ_GGMX",
            columns="ALL",
            filter_str=filter_str,
            sort_columns="DATE",
            sort_types=-1,
            page_size=page_size,
        )

        items = result.get("result", {}).get("data", [])
        data = []
        for item in items:
            data.append({
                "date": item.get("DATE", "")[:10],
                "margin_buy": item.get("RZBUY_AMT", 0),  # 融资买入
                "margin_repay": item.get("RZ_REPAY", 0),  # 融资偿还
                "margin_balance": item.get("RZYE", 0),  # 融资余额
                "short_sell": item.get("RQ_SELL", 0),  # 融券卖出
                "short_repay": item.get("RQ_BUY", 0),  # 融券偿还
                "short_balance": item.get("RQYE", 0),  # 融券余额
            })

        return {
            "code": code,
            "data": data,
            "count": len(data),
            "status": "success",
        }
    except Exception as e:
        logger.error("margin_trading_error", code=code, error=str(e))
        return {"error": f"获取融资融券失败: {e}", "status": "error"}


# ── Block Trade ─────────────────────────────────────────────────


def fetch_block_trade(code: str, page_size: int = 20) -> dict:
    """获取大宗交易数据。

    Args:
        code: 股票代码
        page_size: 返回条数

    Returns:
        {code, trades: [{date, price, volume, amount, premium_rate, buyer, seller}], status}
    """
    try:
        code = _normalize_code(code)

        filter_str = f'(SECURITY_CODE="{code}")'
        result = _eastmoney_datacenter(
            report_name="RPT_BLOCKTRADE_DET",
            columns="ALL",
            filter_str=filter_str,
            sort_columns="TRADE_DATE",
            sort_types=-1,
            page_size=page_size,
        )

        items = result.get("result", {}).get("data", [])
        trades = []
        for item in items:
            trades.append({
                "date": item.get("TRADE_DATE", "")[:10],
                "price": item.get("DEAL_PRICE", 0),
                "volume": item.get("DEAL_VOLUME", 0),
                "amount": item.get("DEAL_AMT", 0),
                "premium_rate": item.get("PREMIUM_RATIO", 0),
                "buyer": item.get("BUYER_NAME", ""),
                "seller": item.get("SELLER_NAME", ""),
            })

        return {
            "code": code,
            "trades": trades,
            "count": len(trades),
            "status": "success",
        }
    except Exception as e:
        logger.error("block_trade_error", code=code, error=str(e))
        return {"error": f"获取大宗交易失败: {e}", "status": "error"}


# ── Holder Number Change ────────────────────────────────────────


def fetch_holder_change(code: str, page_size: int = 10) -> dict:
    """获取股东户数变化。

    Args:
        code: 股票代码
        page_size: 返回期数

    Returns:
        {code, changes: [{date, holder_count, change_pct, avg_hold}], status}
    """
    try:
        code = _normalize_code(code)

        filter_str = f'(SECURITY_CODE="{code}")'
        result = _eastmoney_datacenter(
            report_name="RPT_F10_EH_HOLDERSNUM",
            columns="ALL",
            filter_str=filter_str,
            sort_columns="END_DATE",
            sort_types=-1,
            page_size=page_size,
        )

        items = result.get("result", {}).get("data", [])
        changes = []
        for item in items:
            changes.append({
                "date": item.get("END_DATE", "")[:10],
                "holder_count": item.get("HOLDER_NUM", 0),
                "change_pct": item.get("HOLDER_NUM_RATIO", 0),
                "avg_hold": item.get("AVG_FREE_SHARES", 0),
            })

        return {
            "code": code,
            "changes": changes,
            "count": len(changes),
            "status": "success",
        }
    except Exception as e:
        logger.error("holder_change_error", code=code, error=str(e))
        return {"error": f"获取股东户数失败: {e}", "status": "error"}


# ── Dividend History ────────────────────────────────────────────


def fetch_dividend_history(code: str, page_size: int = 20) -> dict:
    """获取分红送转历史。

    Args:
        code: 股票代码
        page_size: 返回条数

    Returns:
        {code, dividends: [{date, dividend, bonus, transfer, progress}], status}
    """
    try:
        code = _normalize_code(code)

        filter_str = f'(SECURITY_CODE="{code}")'
        result = _eastmoney_datacenter(
            report_name="RPT_SHAREBONUS_DET",
            columns="ALL",
            filter_str=filter_str,
            sort_columns="EX_DIVIDEND_DATE",
            sort_types=-1,
            page_size=page_size,
        )

        items = result.get("result", {}).get("data", [])
        dividends = []
        for item in items:
            dividends.append({
                "date": item.get("EX_DIVIDEND_DATE", "")[:10],
                "dividend": item.get("PRETAX_BONUS_RMB", 0),  # 每股派息(税前)
                "bonus": item.get("BONUS_IT_RATIO", 0),  # 每股送股
                "transfer": item.get("TRANSFER_IT_RATIO", 0),  # 每股转增
                "progress": item.get("IMPL_PLAN_PROFILE", ""),
                "record_date": item.get("EQUITY_RECORD_DATE", "")[:10],
            })

        return {
            "code": code,
            "dividends": dividends,
            "count": len(dividends),
            "status": "success",
        }
    except Exception as e:
        logger.error("dividend_history_error", code=code, error=str(e))
        return {"error": f"获取分红历史失败: {e}", "status": "error"}


# ── Backup Sources ──────────────────────────────────────────────


def fetch_dragon_tiger_backup(trade_date: str) -> dict:
    """获取龙虎榜数据（交易所官方备胎）。

    Args:
        trade_date: 交易日期（YYYY-MM-DD）

    Returns:
        {date, stocks: [{code, name, reason, buy_seats, sell_seats}], status}
    """
    try:
        # Shanghai Exchange
        sh_url = "http://query.sse.com.cn/commonSo498Query.do"
        sh_headers = {"Referer": "http://www.sse.com.cn/", "User-Agent": UA}
        sh_params = {
            "isPagination": "true",
            "sqlId": "COMMON_SSE_ZQPZ_YSHB_LB_TJ_L",
            "tradeDate": trade_date,
            "pageHelp.pageSize": 100,
        }

        # Shenzhen Exchange
        sz_url = "http://www.szse.cn/api/report/ShowReport/data"
        sz_params = {
            "SHOWTYPE": "JSON",
            "CATALOGID": "LHPTJ",
            "TABKEY": "tab1",
            "txtDMorJC": "",
            "txtNLRQ": trade_date,
            "pageSize": 100,
            "pageNum": 1,
        }

        stocks = []

        # Try Shanghai
        try:
            r = requests.get(sh_url, params=sh_params, headers=sh_headers, timeout=15)
            data = r.json()
            for item in data.get("result", []):
                stocks.append({
                    "code": item.get("SECURITY_CODE", ""),
                    "name": item.get("SECURITY_NAME", ""),
                    "market": "SH",
                    "reason": item.get("EXPLAIN", ""),
                })
        except Exception:
            pass

        # Try Shenzhen
        try:
            r = requests.get(sz_url, params=sz_params, headers={"User-Agent": UA}, timeout=15)
            data = r.json()
            if data and len(data) > 0:
                for item in data[0].get("data", []):
                    stocks.append({
                        "code": item.get("zqdm", ""),
                        "name": item.get("zqjc", ""),
                        "market": "SZ",
                        "reason": item.get("yy", ""),
                    })
        except Exception:
            pass

        return {
            "date": trade_date,
            "stocks": stocks,
            "count": len(stocks),
            "status": "success",
        }
    except Exception as e:
        logger.error("dragon_tiger_backup_error", error=str(e))
        return {"error": f"获取龙虎榜失败: {e}", "status": "error"}
