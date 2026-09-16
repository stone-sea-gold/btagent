"""A-share fundamental data tools — reports, financials, valuation.

Data sources:
- 东财 (EastMoney): research reports, industry reports
- 同花顺 (THS): EPS forecasts
- 新浪 (Sina): financial statements

All interfaces are free, no API key required.
"""

import json
import re
import time
import random
from pathlib import Path

import requests

from src.logging import get_logger

logger = get_logger("astock_fundamental")

# ── Constants & Session ─────────────────────────────────────────

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

# EastMoney session with rate limiting
EM_SESSION = requests.Session()
EM_SESSION.headers.update({"User-Agent": UA})
_em_last_call = [0.0]
EM_MIN_INTERVAL = 1.0  # Minimum 1s between EastMoney requests


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


# ── Research Reports ────────────────────────────────────────────


def fetch_stock_reports(code: str, max_pages: int = 3) -> dict:
    """获取个股研报列表（评级、目标价、机构）。

    Args:
        code: 股票代码（如 "600519"）
        max_pages: 最大页数

    Returns:
        {code, reports: [{title, org, rating, target_price, pub_date}], count, status}
    """
    try:
        code = _normalize_code(code)
        url = "https://reportapi.eastmoney.com/report/list"
        all_reports = []

        for page in range(1, max_pages + 1):
            params = {
                "industryCode": "*",
                "pageSize": 50,
                "industry": "*",
                "rating": "*",
                "ratingChange": "*",
                "beginTime": "",
                "endTime": "",
                "pageNo": page,
                "fields": "",
                "qType": 0,
                "orgCode": "",
                "code": code,
                "rcode": "",
                "p": page,
                "pageNum": page,
            }
            r = _em_get(url, params=params, timeout=15)
            data = r.json()

            if data.get("data") is None:
                break

            for item in data["data"]:
                all_reports.append({
                    "title": item.get("title", ""),
                    "org": item.get("orgSName", ""),
                    "rating": item.get("emRatingName", ""),
                    "target_price": item.get("predictThisYearPe", ""),
                    "eps_forecast": item.get("predictThisYearEps", ""),
                    "pub_date": item.get("publishDate", "")[:10],
                    "info_code": item.get("infoCode", ""),
                })

            if page >= data.get("totalPage", 1):
                break

        return {
            "code": code,
            "reports": all_reports[:50],
            "count": len(all_reports),
            "status": "success",
        }
    except Exception as e:
        logger.error("stock_reports_error", code=code, error=str(e))
        return {"error": f"获取研报失败: {e}", "status": "error"}


def fetch_industry_reports(industry_code: str = "*", max_pages: int = 3) -> dict:
    """获取行业研报列表。

    Args:
        industry_code: 东财行业码（如 "1238"），"*" 表示全部行业
        max_pages: 最大页数

    Returns:
        {reports: [{title, org, industry, pub_date}], count, status}
    """
    try:
        url = "https://reportapi.eastmoney.com/report/list"
        all_reports = []

        for page in range(1, max_pages + 1):
            params = {
                "industryCode": industry_code,
                "pageSize": 50,
                "industry": "*",
                "rating": "*",
                "ratingChange": "*",
                "beginTime": "",
                "endTime": "",
                "pageNo": page,
                "fields": "",
                "qType": 1,  # 1 = industry reports
                "orgCode": "",
                "code": "",
                "rcode": "",
                "p": page,
                "pageNum": page,
            }
            r = _em_get(url, params=params, timeout=15)
            data = r.json()

            if data.get("data") is None:
                break

            for item in data["data"]:
                all_reports.append({
                    "title": item.get("title", ""),
                    "org": item.get("orgSName", ""),
                    "industry": item.get("industryName", ""),
                    "pub_date": item.get("publishDate", "")[:10],
                    "info_code": item.get("infoCode", ""),
                })

            if page >= data.get("totalPage", 1):
                break

        return {
            "reports": all_reports[:50],
            "count": len(all_reports),
            "status": "success",
        }
    except Exception as e:
        logger.error("industry_reports_error", error=str(e))
        return {"error": f"获取行业研报失败: {e}", "status": "error"}


def download_report_pdf(info_code: str, target_dir: str = "./reports") -> dict:
    """下载研报PDF。

    Args:
        info_code: 研报信息代码（从 fetch_stock_reports 获取）
        target_dir: 保存目录

    Returns:
        {path, status} 或 {error, status}
    """
    try:
        url = f"https://data.eastmoney.com/report/zw/industry.jshtml?infocode={info_code}"
        pdf_url = f"https://pdf.dfcfw.com/pdf/H3_{info_code}_1.pdf"

        headers = {"Referer": "https://data.eastmoney.com/", "User-Agent": UA}
        r = requests.get(pdf_url, headers=headers, timeout=30)

        if r.status_code == 200 and r.content[:4] == b"%PDF":
            Path(target_dir).mkdir(parents=True, exist_ok=True)
            path = Path(target_dir) / f"{info_code}.pdf"
            path.write_bytes(r.content)
            return {"path": str(path), "size_kb": len(r.content) // 1024, "status": "success"}
        else:
            return {"error": "PDF下载失败或不存在", "status": "not_found"}
    except Exception as e:
        logger.error("pdf_download_error", info_code=info_code, error=str(e))
        return {"error": f"PDF下载失败: {e}", "status": "error"}


# ── EPS Forecast ────────────────────────────────────────────────


def fetch_eps_forecast(code: str) -> dict:
    """获取机构一致预期EPS。

    Args:
        code: 股票代码

    Returns:
        {code, eps_current_year, eps_next_year, pe_forecast, status}
    """
    try:
        code = _normalize_code(code)
        prefix = _get_prefix(code)

        # THS API
        url = f"https://basic.10jqka.com.cn/api/stockph/main/{prefix}{code}/forecast"
        headers = {"User-Agent": UA, "Referer": "https://basic.10jqka.com.cn/"}
        r = requests.get(url, headers=headers, timeout=15)
        data = r.json()

        if data.get("status_code") != 0:
            return {"error": "获取EPS预测失败", "status": "error"}

        result = data.get("data", {})
        return {
            "code": code,
            "eps_current_year": result.get("eps_this_year", ""),
            "eps_next_year": result.get("eps_next_year", ""),
            "pe_current_year": result.get("pe_this_year", ""),
            "pe_next_year": result.get("pe_next_year", ""),
            "rating": result.get("rating", ""),
            "org_count": result.get("org_count", ""),
            "status": "success",
        }
    except Exception as e:
        logger.error("eps_forecast_error", code=code, error=str(e))
        return {"error": f"获取EPS预测失败: {e}", "status": "error"}


# ── Financial Statements ────────────────────────────────────────


def fetch_financial_statements(code: str, report_type: str = "lrb", num: int = 4) -> dict:
    """获取财报三表（新浪源）。

    Args:
        code: 股票代码
        report_type: "lrb"(利润表), "zcfz"(资产负债表), "xjll"(现金流量表)
        num: 获取期数

    Returns:
        {code, report_type, periods: [{period, items: [{name, value}]}], status}
    """
    try:
        code = _normalize_code(code)
        prefix = _get_prefix(code)

        type_map = {
            "lrb": "lrb",  # 利润表
            "zcfz": "zcfz",  # 资产负债表
            "xjll": "xjll",  # 现金流量表
        }
        rt = type_map.get(report_type, "lrb")

        url = f"https://quotes.sina.cn/cn/go.php/vFD_FinanceSummary/stockid/{prefix}{code}/type/{rt}.phtml"
        headers = {"User-Agent": UA}
        r = requests.get(url, headers=headers, timeout=15)
        r.encoding = "gb2312"

        # Parse HTML table
        from io import StringIO
        import pandas as pd

        tables = pd.read_html(StringIO(r.text))
        if not tables:
            return {"error": "未找到财务数据", "status": "not_found"}

        df = tables[0]
        periods = []
        for col in df.columns[1:num+1]:
            items = []
            for _, row in df.iterrows():
                items.append({
                    "name": str(row.iloc[0]),
                    "value": str(row[col]) if pd.notna(row[col]) else "",
                })
            periods.append({"period": str(col), "items": items})

        return {
            "code": code,
            "report_type": report_type,
            "periods": periods,
            "status": "success",
        }
    except Exception as e:
        logger.error("financial_stmt_error", code=code, error=str(e))
        return {"error": f"获取财报失败: {e}", "status": "error"}


# ── Valuation ───────────────────────────────────────────────────


def fetch_valuation(code: str) -> dict:
    """获取完整估值分析（PE/PEG/消化时间）。

    Args:
        code: 股票代码

    Returns:
        {code, pe_ttm, eps_forecast, growth_rate, peg, pe_digestion_years, status}
    """
    try:
        code = _normalize_code(code)
        prefix = _get_prefix(code)

        # Get current price from Tencent
        url = f"https://qt.gtimg.cn/q={prefix}{code}"
        r = requests.get(url, timeout=10)
        parts = r.text.split("~")

        if len(parts) < 50:
            return {"error": "获取行情失败", "status": "error"}

        price = float(parts[3]) if parts[3] else 0
        pe_ttm = float(parts[39]) if parts[39] else 0

        # Get EPS forecast
        eps_data = fetch_eps_forecast(code)
        eps_forecast = 0
        if eps_data.get("status") == "success":
            try:
                eps_forecast = float(eps_data.get("eps_current_year", 0) or 0)
            except (ValueError, TypeError):
                pass

        # Calculate PEG (assume 15% growth if not available)
        growth_rate = 15.0
        peg = pe_ttm / growth_rate if pe_ttm > 0 and growth_rate > 0 else 0

        # Calculate PE digestion years (to PE=20)
        target_pe = 20
        pe_digestion = 0
        if pe_ttm > target_pe and growth_rate > 0:
            pe_digestion = (pe_ttm - target_pe) / growth_rate

        return {
            "code": code,
            "price": price,
            "pe_ttm": round(pe_ttm, 2),
            "eps_forecast": eps_forecast,
            "growth_rate": growth_rate,
            "peg": round(peg, 2),
            "pe_digestion_years": round(pe_digestion, 1),
            "status": "success",
        }
    except Exception as e:
        logger.error("valuation_error", code=code, error=str(e))
        return {"error": f"估值分析失败: {e}", "status": "error"}
