"""Market data tools for the Agent — pytdx as primary source.

Provides real-time quotes, historical K-lines, financial data,
sector flows, industry stocks, and index constituents.
Uses pytdx (pure Python, TDX protocol) as primary source.
"""

from contextlib import contextmanager

from src.logging import get_logger

logger = get_logger("market_data_tools")

# ── pytdx Client Management ─────────────────────────────────────

_tdx_api = None
_stock_name_cache = {}  # {symbol: name}

# TDX servers (auto-fallback)
TDX_SERVERS = [
    ('218.75.126.9', 7709),
    ('115.238.56.198', 7709),
    ('124.160.88.183', 7709),
    ('119.147.212.81', 7709),
    ('114.80.63.12', 7709),
]


def _get_tdx_api():
    """Get or create pytdx API instance (lazy init, auto-reconnect with server fallback)."""
    global _tdx_api
    if _tdx_api is None:
        from pytdx.hq import TdxHq_API
        for host, port in TDX_SERVERS:
            try:
                api = TdxHq_API()
                api.connect(host, port)
                # Test connection
                test = api.get_security_quotes([(1, '600519')])
                if test:
                    _tdx_api = api
                    logger.info("pytdx_connected", server=f"{host}:{port}")
                    return _tdx_api
                api.disconnect()
            except Exception as e:
                logger.debug("pytdx_server_failed", server=f"{host}:{port}", error=str(e))
                continue
        raise ConnectionError("无法连接到任何 TDX 服务器")
    return _tdx_api


def _reset_tdx_api():
    """Reset client on error (will reconnect on next call)."""
    global _tdx_api
    if _tdx_api:
        try:
            _tdx_api.disconnect()
        except:
            pass
    _tdx_api = None


def _market_code(symbol: str) -> int:
    """Convert stock symbol to pytdx market code."""
    if symbol.startswith(("6", "5")):
        return 1  # Shanghai
    return 0  # Shenzhen


# Common stock names (hardcoded for key stocks)
_STOCK_NAMES = {
    '600519': '贵州茅台',
    '601318': '中国平安',
    '600036': '招商银行',
    '000858': '五粮液',
    '000333': '美的集团',
    '601166': '兴业银行',
    '600276': '恒瑞医药',
    '000001': '平安银行',
    '600030': '中信证券',
    '601398': '工商银行',
}


def _get_stock_name(symbol: str) -> str:
    """Get stock name (from cache or common stocks)."""
    if symbol in _stock_name_cache:
        return _stock_name_cache[symbol]
    # Return from hardcoded list or empty
    return _STOCK_NAMES.get(symbol, "")


# ── Public API ──────────────────────────────────────────────────


def fetch_stock_quote(symbol: str) -> dict:
    """Get real-time quote for a single stock."""
    try:
        api = _get_tdx_api()
        market = _market_code(symbol)

        quotes = api.get_security_quotes([(market, symbol)])
        if not quotes or len(quotes) == 0:
            return {"error": f"未找到股票 {symbol}", "status": "not_found"}

        q = quotes[0]
        last_close = q.get("last_close", 0)
        price = q.get("price", 0)

        return {
            "symbol": symbol,
            "name": _get_stock_name(symbol),
            "price": price,
            "change_pct": round((price / last_close - 1) * 100, 2) if last_close else 0,
            "change_amount": round(price - last_close, 2),
            "volume": q.get("vol", 0),
            "turnover": q.get("amount", 0),
            "turnover_rate": 0,  # pytdx doesn't provide this directly
            "pe_ratio": 0,
            "pb_ratio": 0,
            "total_market_cap": 0,
            "status": "success",
        }
    except Exception as e:
        logger.error("quote_error", symbol=symbol, error=str(e))
        _reset_tdx_api()
        return {"error": f"数据获取失败: {e}", "status": "error"}


def fetch_stock_hist(
    symbol: str, start: str = "", end: str = "",
    period: str = "daily", adjust: str = "qfq",
) -> dict:
    """Get historical K-line data for a stock.

    Args:
        symbol: Stock code (e.g., "600519")
        start: Start date YYYYMMDD (default: 1 year ago)
        end: End date YYYYMMDD (default: today)
        period: "daily", "weekly", "monthly"
        adjust: "qfq" (forward), "hfq" (backward), "" (none)
    """
    try:
        api = _get_tdx_api()
        market = _market_code(symbol)

        # Map period
        category_map = {
            "daily": 9,
            "weekly": 5,
            "monthly": 6,
        }
        category = category_map.get(period, 9)

        # Get data (pytdx returns up to 800 bars per call)
        df = api.to_df(api.get_security_bars(category, market, symbol, 0, 800))

        if df is None or df.empty:
            return {"error": f"未找到 {symbol} 的K线数据", "status": "not_found"}

        # Filter by date if specified
        if start or end:
            df["date_str"] = df["datetime"].astype(str).str[:10].str.replace("-", "")
            if start:
                df = df[df["date_str"] >= start]
            if end:
                df = df[df["date_str"] <= end]

        # Build result
        records = []
        for _, row in df.iterrows():
            records.append({
                "date": str(row.get("datetime", ""))[:10],
                "open": float(row.get("open", 0)),
                "high": float(row.get("high", 0)),
                "low": float(row.get("low", 0)),
                "close": float(row.get("close", 0)),
                "volume": float(row.get("vol", 0)),
                "turnover": float(row.get("amount", 0)),
                "change_pct": 0,  # Calculate if needed
            })

        return {
            "symbol": symbol,
            "period": period,
            "adjust": adjust,
            "data": records,
            "count": len(records),
            "status": "success",
        }
    except Exception as e:
        logger.error("hist_error", symbol=symbol, error=str(e))
        _reset_tdx_api()
        return {"error": f"数据获取失败: {e}", "status": "error"}


def fetch_financial_summary(symbol: str) -> dict:
    """Get financial summary for a stock."""
    try:
        api = _get_tdx_api()
        market = _market_code(symbol)

        # Get finance info
        info = api.get_finance_info(market, symbol)
        if not info:
            return {"error": f"未找到 {symbol} 的财务数据", "status": "not_found"}

        return {
            "symbol": symbol,
            "name": info.get("name", ""),
            "pe_ratio": 0,  # pytdx basic finance doesn't have PE
            "pb_ratio": 0,
            "total_market_cap": 0,
            "circulating_market_cap": 0,
            "status": "success",
        }
    except Exception as e:
        logger.error("financial_error", symbol=symbol, error=str(e))
        _reset_tdx_api()
        return {"error": f"数据获取失败: {e}", "status": "error"}


def fetch_sector_flow(date: str = "") -> dict:
    """Get sector/industry list data (板块列表)."""
    try:
        api = _get_tdx_api()

        # Get sector list (use block.dat for industry sectors)
        sectors = api.get_and_parse_block_info("block.dat")
        if not sectors:
            return {"error": "获取板块数据失败", "status": "error"}

        # Deduplicate by blockname, collect unique sectors
        seen = set()
        result = []
        for sector in sectors:
            name = sector.get("blockname", "")
            if name and name not in seen:
                seen.add(name)
                result.append({
                    "name": name,
                    "code": sector.get("code", ""),
                })
            if len(result) >= 30:
                break

        return {"data": result, "count": len(result), "status": "success"}
    except Exception as e:
        logger.error("sector_error", error=str(e))
        _reset_tdx_api()
        return {"error": f"数据获取失败: {e}", "status": "error"}


# ── baostock Tools ──────────────────────────────────────────────


@contextmanager
def _baostock_session():
    """Context manager for baostock login/logout."""
    import baostock as bs
    bs.login()
    try:
        yield bs
    finally:
        bs.logout()


def fetch_quarterly_financials(symbol: str, year: int = 0, quarter: int = 0) -> dict:
    """Get quarterly financial indicators for a stock."""
    try:
        from datetime import datetime
        if not year:
            year = datetime.now().year
        if not quarter:
            quarter = (datetime.now().month - 1) // 3 + 1

        if not symbol.startswith(("sh.", "sz.", "bj.")):
            if symbol.startswith("6"):
                symbol = f"sh.{symbol}"
            else:
                symbol = f"sz.{symbol}"

        with _baostock_session() as bs:
            rs = bs.query_profit_data(code=symbol, year=year, quarter=quarter)
            if rs.error_code != "0":
                return {"error": f"baostock 查询失败: {rs.error_msg}", "status": "error"}

            records = []
            while rs.next():
                records.append(rs.get_row_data())

            if not records:
                return {"error": f"未找到 {symbol} {year}Q{quarter} 的财务数据", "status": "not_found"}

            fields = rs.fields
            return {"symbol": symbol, "year": year, "quarter": quarter, "data": dict(zip(fields, records[0])), "status": "success"}
    except ImportError:
        return {"error": "baostock 未安装，请运行: pip install baostock", "status": "error"}
    except Exception as e:
        logger.error("baostock_error", symbol=symbol, error=str(e))
        return {"error": f"数据获取失败: {e}", "status": "error"}


def fetch_industry_stocks(industry: str) -> dict:
    """Get stocks in a specific industry (fuzzy match).

    Baostock returns industry codes like 'J66货币金融服务', so we match
    if the industry name contains the query or vice versa.
    """
    try:
        import baostock as bs
        with _baostock_session() as bs:
            rs = bs.query_stock_industry()
            if rs.error_code != "0":
                return {"error": f"baostock 查询失败: {rs.error_msg}", "status": "error"}

            records = []
            while rs.next():
                row = rs.get_row_data()
                if len(row) >= 4:
                    industry_code = row[3] if row[3] else ""
                    # Fuzzy match: check if query is in industry code or vice versa
                    if industry in industry_code or industry_code in industry:
                        records.append({
                            "code": row[1],
                            "name": row[2],
                            "industry": industry_code,
                        })

            return {"industry": industry, "data": records[:100], "count": len(records), "status": "success"}
    except ImportError:
        return {"error": "baostock 未安装，请运行: pip install baostock", "status": "error"}
    except Exception as e:
        logger.error("industry_error", industry=industry, error=str(e))
        return {"error": f"数据获取失败: {e}", "status": "error"}


def fetch_index_constituents(index: str = "csi300") -> dict:
    """Get index constituent stocks."""
    try:
        import baostock as bs
        from datetime import datetime
        date = datetime.now().strftime("%Y-%m-%d")

        with _baostock_session() as bs:
            if index == "csi300":
                rs = bs.query_hs300_stocks(date=date)
            elif index == "csi500":
                rs = bs.query_zz500_stocks(date=date)
            else:
                rs = bs.query_hs300_stocks(date=date)

            if rs.error_code != "0":
                return {"error": f"baostock 查询失败: {rs.error_msg}", "status": "error"}

            records = []
            while rs.next():
                row = rs.get_row_data()
                if len(row) >= 2:
                    records.append({"code": row[1], "name": row[2] if len(row) > 2 else ""})

            return {"index": index, "date": date, "data": records[:500], "count": len(records), "status": "success"}
    except ImportError:
        return {"error": "baostock 未安装，请运行: pip install baostock", "status": "error"}
    except Exception as e:
        logger.error("index_error", index=index, error=str(e))
        return {"error": f"数据获取失败: {e}", "status": "error"}
