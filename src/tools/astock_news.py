"""A-share news & announcement tools — stock news, market telegraph, announcements.

Data sources:
- 东财 (EastMoney): stock news, global news, hot rank
- 财联社 (CLS): market telegraph
- 巨潮 (CNINFO): announcements

All interfaces are free, no API key required.
"""

import json
import re
import time
import random
from datetime import datetime

import requests

from src.logging import get_logger

logger = get_logger("astock_news")

# ── Constants & Session ─────────────────────────────────────────

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

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


# ── Stock News ──────────────────────────────────────────────────


def fetch_stock_news(code: str, page_size: int = 20) -> dict:
    """获取个股新闻。

    Args:
        code: 股票代码
        page_size: 返回条数

    Returns:
        {code, news: [{title, summary, time, source, url}], status}
    """
    try:
        code = _normalize_code(code)

        cb = "jQuery_news"
        url = "https://search-api-web.eastmoney.com/search/jsonp"
        inner_params = json.dumps({
            "uid": "",
            "keyword": code,
            "type": ["cmsArticleWebOld"],
            "client": "web",
            "clientType": "web",
            "clientVersion": "curr",
            "param": {
                "cmsArticleWebOld": {
                    "searchScope": "default",
                    "sort": "default",
                    "pageIndex": 1,
                    "pageSize": page_size,
                    "preTag": "",
                    "postTag": "",
                }
            },
        }, separators=(',', ':'))
        params = {"cb": cb, "param": inner_params}
        headers = {"User-Agent": UA, "Referer": "https://so.eastmoney.com/"}
        r = _em_get(url, params=params, headers=headers, timeout=15)

        # Parse JSONP
        text = r.text
        json_str = text[text.index("(") + 1:text.rindex(")")]
        d = json.loads(json_str)

        news = []
        articles = d.get("result", {}).get("cmsArticleWebOld", []) or []
        for a in articles:
            news.append({
                "title": re.sub(r'<[^>]+>', '', a.get("title", "")),
                "summary": re.sub(r'<[^>]+>', '', a.get("content", ""))[:200],
                "time": a.get("date", ""),
                "source": a.get("mediaName", ""),
                "url": a.get("url", ""),
            })

        return {
            "code": code,
            "news": news,
            "count": len(news),
            "status": "success",
        }
    except Exception as e:
        logger.error("stock_news_error", code=code, error=str(e))
        return {"error": f"获取个股新闻失败: {e}", "status": "error"}


# ── Market Telegraph ────────────────────────────────────────────


def fetch_market_telegraph(page_size: int = 50) -> dict:
    """获取财联社全市场快讯。

    Args:
        page_size: 返回条数

    Returns:
        {news: [{title, content, time, level}], status}
    """
    try:
        url = "https://www.cls.cn/nodeapi/updateTelegraphList"
        params = {
            "app": "CailianpressWeb",
            "os": "web",
            "sv": "7.7.5",
            "rn": page_size,
        }
        headers = {"User-Agent": UA, "Referer": "https://www.cls.cn/"}
        r = requests.get(url, params=params, headers=headers, timeout=15)
        data = r.json()

        news = []
        for item in data.get("data", {}).get("roll_data", []):
            content = item.get("content", "")
            # Remove HTML tags
            content = re.sub(r'<[^>]+>', '', content)
            news.append({
                "title": item.get("title", "") or content[:50],
                "content": content,
                "time": datetime.fromtimestamp(item.get("ctime", 0)).strftime("%Y-%m-%d %H:%M") if item.get("ctime") else "",
                "level": item.get("level", ""),
            })

        return {
            "news": news,
            "count": len(news),
            "status": "success",
        }
    except Exception as e:
        logger.error("telegraph_error", error=str(e))
        return {"error": f"获取财联社快讯失败: {e}", "status": "error"}


# ── Global News ─────────────────────────────────────────────────


def fetch_global_news(page_size: int = 50) -> dict:
    """获取东财全球财经资讯（7×24）。

    Args:
        page_size: 返回条数

    Returns:
        {news: [{title, content, time, source}], status}
    """
    try:
        url = "https://np-listapi.eastmoney.com/comm/web/getNewsByColumns"
        params = {
            "columns": "74,467",
            "pageSize": page_size,
            "pageIndex": 0,
            "needContent": "1",
        }
        headers = {"User-Agent": UA}
        r = _em_get(url, params=params, headers=headers, timeout=15)
        data = r.json()

        news = []
        for item in data.get("data", {}).get("list", []):
            news.append({
                "title": item.get("title", ""),
                "content": item.get("digest", "")[:200],
                "time": item.get("showTime", ""),
                "source": item.get("source", ""),
                "url": item.get("url", ""),
            })

        return {
            "news": news,
            "count": len(news),
            "status": "success",
        }
    except Exception as e:
        logger.error("global_news_error", error=str(e))
        return {"error": f"获取全球资讯失败: {e}", "status": "error"}


# ── Announcements ───────────────────────────────────────────────


def _cninfo_orgid(code: str) -> str:
    """Get CNINFO orgId for a stock code."""
    try:
        # Try official mapping
        url = "http://www.cninfo.com.cn/new/data/szse_stock.json"
        r = requests.get(url, headers={"User-Agent": UA}, timeout=10)
        data = r.json()

        for stock in data.get("stockList", []):
            if stock.get("code") == code:
                return stock.get("orgId", "")

        # Fallback to hardcoded pattern
        if code.startswith("6"):
            return f"9900{code}"
        else:
            return f"gssz{code}"
    except Exception:
        return f"gssz{code}"


def fetch_announcements(code: str, page_size: int = 20) -> dict:
    """获取公司公告（巨潮源）。

    Args:
        code: 股票代码
        page_size: 返回条数

    Returns:
        {code, announcements: [{title, time, type, url}], status}
    """
    try:
        code = _normalize_code(code)
        org_id = _cninfo_orgid(code)

        url = "http://www.cninfo.com.cn/new/hisAnnouncement/query"
        data = {
            "stock": f"{code},{org_id}",
            "tabName": "fulltext",
            "pageSize": page_size,
            "pageNum": 1,
            "column": "szse" if code.startswith(("0", "3")) else "sse",
            "category": "",
            "plate": "",
            "seDate": "",
            "searchkey": "",
            "secid": "",
            "sortName": "",
            "sortType": "",
            "isHLtitle": "true",
        }
        headers = {"User-Agent": UA, "Referer": "http://www.cninfo.com.cn/"}
        r = requests.post(url, data=data, headers=headers, timeout=15)
        result = r.json()

        announcements = []
        for item in result.get("announcements", []) or []:
            announcements.append({
                "title": item.get("announcementTitle", ""),
                "time": datetime.fromtimestamp(
                    item.get("announcementTime", 0) / 1000
                ).strftime("%Y-%m-%d %H:%M") if item.get("announcementTime") else "",
                "type": item.get("announcementTypeName", ""),
                "url": f"http://static.cninfo.com.cn/{item.get('adjunctUrl', '')}",
            })

        return {
            "code": code,
            "announcements": announcements,
            "count": len(announcements),
            "status": "success",
        }
    except Exception as e:
        logger.error("announcements_error", code=code, error=str(e))
        return {"error": f"获取公告失败: {e}", "status": "error"}


# ── Hot Lists ───────────────────────────────────────────────────


def fetch_hot_list(period: str = "hour") -> dict:
    """获取同花顺热榜。

    Args:
        period: 时间周期（hour/daily）

    Returns:
        {stocks: [{code, name, hot_value, rank, concept}], status}
    """
    try:
        url = "https://dq.10jqka.com.cn/fuyao/hot_list_data/out/hot_list/v1/stock"
        params = {
            "stock_type": "a",
            "type": period,
            "list_type": "normal",
        }
        headers = {"User-Agent": UA, "Referer": "https://www.10jqka.com.cn/"}
        r = requests.get(url, params=params, headers=headers, timeout=15)
        data = r.json()

        stocks = []
        for item in data.get("data", {}).get("stock_list", []):
            stocks.append({
                "code": item.get("code", ""),
                "name": item.get("name", ""),
                "hot_value": item.get("hot_value", 0),
                "rank": item.get("order", 0),
                "concept": item.get("reason", ""),
            })

        return {
            "stocks": stocks,
            "count": len(stocks),
            "status": "success",
        }
    except Exception as e:
        logger.error("hot_list_error", error=str(e))
        return {"error": f"获取热榜失败: {e}", "status": "error"}


def fetch_hot_rank(top: int = 50) -> dict:
    """获取东财人气榜。

    Args:
        top: 返回前N名

    Returns:
        {stocks: [{code, name, rank, rank_change, price}], status}
    """
    try:
        url = "https://emappdata.eastmoney.com/stockrank/getAllCurrentList"
        data = {
            "appId": "appId01",
            "globalId": "786e4c21-70dc-435a-93bb-38",
            "marketType": "",
            "pageNo": 1,
            "pageSize": top,
        }
        headers = {"User-Agent": UA, "Content-Type": "application/json"}
        r = requests.post(url, json=data, headers=headers, timeout=15)
        result = r.json()

        stocks = []
        for item in result.get("data", []):
            stocks.append({
                "code": item.get("sc", ""),
                "name": item.get("sn", ""),
                "rank": item.get("rk", 0),
                "rank_change": item.get("rc", 0),
                "price": item.get("sp", 0),
            })

        return {
            "stocks": stocks,
            "count": len(stocks),
            "status": "success",
        }
    except Exception as e:
        logger.error("hot_rank_error", error=str(e))
        return {"error": f"获取人气榜失败: {e}", "status": "error"}


def fetch_hot_concept(code: str) -> dict:
    """获取个股概念命中（当前市场归到哪些概念在炒）。

    Args:
        code: 股票代码

    Returns:
        {code, concepts: [{name, hot_value}], status}
    """
    try:
        code = _normalize_code(code)

        url = "https://push2.eastmoney.com/api/qt/slist/get"
        params = {
            "spt": "3",
            "fields": "f12,f14,f3",
            "secid": f"{'1' if code.startswith('6') else '0'}.{code}",
        }
        r = _em_get(url, params=params, timeout=15)
        data = r.json()

        concepts = []
        for item in data.get("data", {}).get("diff", []):
            concepts.append({
                "code": item.get("f12", ""),
                "name": item.get("f14", ""),
                "change_pct": item.get("f3", 0) / 100 if item.get("f3") else 0,
            })

        return {
            "code": code,
            "concepts": concepts,
            "count": len(concepts),
            "status": "success",
        }
    except Exception as e:
        logger.error("hot_concept_error", code=code, error=str(e))
        return {"error": f"获取概念命中失败: {e}", "status": "error"}


# ── Backup Sources ──────────────────────────────────────────────


def fetch_announcements_backup(code: str, page_size: int = 20) -> dict:
    """获取公司公告（备胎源：深市走深交所官方，沪市走东财）。

    Args:
        code: 股票代码
        page_size: 返回条数

    Returns:
        {code, announcements: [{title, time, url}], status}
    """
    try:
        code = _normalize_code(code)

        if code.startswith(("0", "3")):
            # Shenzhen Exchange official
            url = "http://www.szse.cn/api/report/ShowReport/data"
            params = {
                "SHOWTYPE": "JSON",
                "CATALOGID": "1801_cw",
                "TABKEY": "tab1",
                "txtDMorJC": code,
                "pageSize": page_size,
                "pageNum": 1,
            }
            r = requests.get(url, params=params, headers={"User-Agent": UA}, timeout=15)
            data = r.json()

            announcements = []
            if data and len(data) > 0:
                for item in data[0].get("data", []):
                    announcements.append({
                        "title": item.get("ggbt", ""),
                        "time": item.get("fbrq", ""),
                        "url": item.get("attachpath", ""),
                    })
        else:
            # Shanghai - use EastMoney
            result = fetch_announcements(code, page_size)
            return result

        return {
            "code": code,
            "announcements": announcements,
            "count": len(announcements),
            "status": "success",
        }
    except Exception as e:
        logger.error("announcements_backup_error", code=code, error=str(e))
        return {"error": f"获取公告失败: {e}", "status": "error"}
