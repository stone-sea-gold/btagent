"""TradingCalendar — Chinese A-share market trading calendar.

Provides:
- Trading day detection (excludes weekends and holidays)
- Latest trading day resolution
- Trading day range queries
- Relative date parsing ("最近一个交易日", "上个月", "今年以来")

Uses a combination of:
- Weekend exclusion (Saturday/Sunday)
- Predefined Chinese market holidays (2020-2026)
- Qlib's trading calendar (if available)
"""

from datetime import datetime, timedelta
from pathlib import Path

from src.config import settings
from src.logging import get_logger

logger = get_logger("trading_calendar")

logger = get_logger("trading_calendar")

# Chinese A-share market holidays (2020-2026)
# Format: set of date strings "YYYY-MM-DD"
_CHINESE_HOLIDAYS = {
    # 2020
    "2020-01-01", "2020-01-24", "2020-01-27", "2020-01-28", "2020-01-29", "2020-01-30", "2020-01-31",
    "2020-04-06", "2020-05-01", "2020-05-04", "2020-05-05", "2020-06-25", "2020-06-26",
    "2020-10-01", "2020-10-02", "2020-10-05", "2020-10-06", "2020-10-07", "2020-10-08",
    # 2021
    "2021-01-01", "2021-02-11", "2021-02-12", "2021-02-15", "2021-02-16", "2021-02-17",
    "2021-04-05", "2021-05-03", "2021-05-04", "2021-05-05", "2021-06-14",
    "2021-09-20", "2021-09-21", "2021-10-01", "2021-10-04", "2021-10-05", "2021-10-06", "2021-10-07",
    # 2022
    "2022-01-03", "2022-01-31", "2022-02-01", "2022-02-02", "2022-02-03", "2022-02-04",
    "2022-04-04", "2022-04-05", "2022-05-02", "2022-05-03", "2022-05-04", "2022-06-03",
    "2022-09-12", "2022-10-03", "2022-10-04", "2022-10-05", "2022-10-06", "2022-10-07",
    # 2023
    "2023-01-02", "2023-01-23", "2023-01-24", "2023-01-25", "2023-01-26", "2023-01-27",
    "2023-04-05", "2023-05-01", "2023-05-02", "2023-05-03", "2023-06-22", "2023-06-23",
    "2023-09-29", "2023-10-02", "2023-10-03", "2023-10-04", "2023-10-05", "2023-10-06",
    # 2024
    "2024-01-01", "2024-02-09", "2024-02-12", "2024-02-13", "2024-02-14", "2024-02-15", "2024-02-16",
    "2024-04-04", "2024-04-05", "2024-05-01", "2024-05-02", "2024-05-03", "2024-06-10",
    "2024-09-16", "2024-09-17", "2024-10-01", "2024-10-02", "2024-10-03", "2024-10-04", "2024-10-07",
    # 2025
    "2025-01-01", "2025-01-28", "2025-01-29", "2025-01-30", "2025-01-31",
    "2025-02-03", "2025-02-04", "2025-04-04", "2025-05-01", "2025-05-02", "2025-05-05",
    "2025-06-02", "2025-10-01", "2025-10-02", "2025-10-03", "2025-10-06", "2025-10-07", "2025-10-08",
    # 2026
    "2026-01-01", "2026-01-02", "2026-02-17", "2026-02-18", "2026-02-19", "2026-02-20",
    "2026-04-06", "2026-05-01", "2026-06-19",
    "2026-10-01", "2026-10-02", "2026-10-05", "2026-10-06", "2026-10-07",
}


class TradingCalendar:
    """Chinese A-share market trading calendar."""

    def __init__(self):
        self._holidays = _CHINESE_HOLIDAYS
        self._qlib_calendar = None
        self._data_coverage_end = None
        self._try_load_qlib_calendar()

    def _try_load_qlib_calendar(self):
        """Try to load Qlib's trading calendar for more accurate data."""
        try:
            import qlib
            from qlib.data import Cal
            self._qlib_calendar = Cal
        except Exception:
            pass

    def get_data_coverage(self) -> dict:
        """Get the actual data coverage from Qlib.

        Returns:
            Dict with 'start_date', 'end_date', and 'is_stale' flag.
        """
        try:
            import qlib
            from qlib.data import Cal
            cal = Cal.calendar()
            if len(cal) > 0:
                latest = str(cal[-1])[:10]  # YYYY-MM-DD
                earliest = str(cal[0])[:10]
                today = datetime.now().strftime("%Y-%m-%d")
                # Data is stale if latest date is more than 3 days behind today
                latest_dt = datetime.strptime(latest, "%Y-%m-%d")
                today_dt = datetime.strptime(today, "%Y-%m-%d")
                is_stale = (today_dt - latest_dt).days > 3

                return {
                    "start_date": earliest,
                    "end_date": latest,
                    "is_stale": is_stale,
                    "days_behind": (today_dt - latest_dt).days,
                    "status": "success",
                }
        except Exception:
            pass

        # Fallback: no Qlib data available
        return {
            "start_date": None,
            "end_date": None,
            "is_stale": True,
            "days_behind": None,
            "status": "no_data",
        }

    def validate_date_against_coverage(self, requested_date: str) -> dict:
        """Check if a requested date is within Qlib's data coverage.

        Args:
            requested_date: The date the user wants to use (YYYY-MM-DD).

        Returns:
            Dict with validation result and recommendation.
        """
        coverage = self.get_data_coverage()

        if coverage["status"] == "no_data":
            return {
                "valid": False,
                "requested_date": requested_date,
                "message": "未找到 Qlib 数据。请先运行 `python cli.py --init-data` 下载数据。",
                "recommendation": "init_data",
            }

        if coverage["end_date"] is None:
            return {"valid": True, "requested_date": requested_date, "message": "无法验证数据覆盖范围，继续执行。"}

        if requested_date > coverage["end_date"]:
            return {
                "valid": False,
                "requested_date": requested_date,
                "data_end_date": coverage["end_date"],
                "days_behind": coverage["days_behind"],
                "message": (
                    f"请求日期 {requested_date} 超出数据覆盖范围。"
                    f"当前数据最新日期为 {coverage['end_date']}（滞后 {coverage['days_behind']} 天）。"
                    f"建议更新数据后重试，或使用 {coverage['end_date']} 作为查询日期。"
                ),
                "recommendation": "update_data_or_use_available",
                "suggested_date": coverage["end_date"],
            }

        return {
            "valid": True,
            "requested_date": requested_date,
            "data_end_date": coverage["end_date"],
            "message": f"日期 {requested_date} 在数据覆盖范围内（数据截至 {coverage['end_date']}）。",
        }

    def is_trading_day(self, date: str) -> bool:
        """Check if a date is a trading day.

        Args:
            date: Date string in YYYY-MM-DD format.

        Returns:
            True if the date is a trading day.
        """
        dt = datetime.strptime(date, "%Y-%m-%d")

        # Check weekend
        if dt.weekday() >= 5:  # Saturday=5, Sunday=6
            return False

        # Check holiday
        if date in self._holidays:
            return False

        return True

    def get_latest_trading_day(self, date: str | None = None) -> str:
        """Get the most recent trading day on or before the given date.

        Args:
            date: Reference date (YYYY-MM-DD). Defaults to today.

        Returns:
            Date string of the latest trading day.
        """
        if date is None:
            dt = datetime.now()
        else:
            dt = datetime.strptime(date, "%Y-%m-%d")

        # Walk backwards to find a trading day
        for _ in range(30):  # Max 30 days back
            date_str = dt.strftime("%Y-%m-%d")
            if self.is_trading_day(date_str):
                return date_str
            dt -= timedelta(days=1)

        return dt.strftime("%Y-%m-%d")

    def get_next_trading_day(self, date: str) -> str:
        """Get the next trading day after the given date.

        Args:
            date: Reference date (YYYY-MM-DD).

        Returns:
            Date string of the next trading day.
        """
        dt = datetime.strptime(date, "%Y-%m-%d") + timedelta(days=1)

        for _ in range(30):
            date_str = dt.strftime("%Y-%m-%d")
            if self.is_trading_day(date_str):
                return date_str
            dt += timedelta(days=1)

        return dt.strftime("%Y-%m-%d")

    def get_first_trading_day_on_or_after(self, date: str) -> str:
        """Get the first trading day on or after the given date.

        Args:
            date: Reference date (YYYY-MM-DD).

        Returns:
            Date string of the first trading day on or after the date.
        """
        dt = datetime.strptime(date, "%Y-%m-%d")

        for _ in range(30):
            date_str = dt.strftime("%Y-%m-%d")
            if self.is_trading_day(date_str):
                return date_str
            dt += timedelta(days=1)

        return dt.strftime("%Y-%m-%d")

    def get_trading_days(self, start_date: str, end_date: str) -> list[str]:
        """Get all trading days in a date range.

        Args:
            start_date: Start date (YYYY-MM-DD, inclusive).
            end_date: End date (YYYY-MM-DD, inclusive).

        Returns:
            List of trading day date strings.
        """
        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d")

        trading_days = []
        current = start
        while current <= end:
            date_str = current.strftime("%Y-%m-%d")
            if self.is_trading_day(date_str):
                trading_days.append(date_str)
            current += timedelta(days=1)

        return trading_days

    def parse_relative_date(self, expression: str, reference_date: str | None = None) -> str | tuple[str, str]:
        """Parse a relative date expression into absolute date(s).

        Supported expressions:
        - "今天" / "今日"
        - "昨天" / "昨日"
        - "最近一个交易日" / "最新交易日"
        - "上个月" / "上月"
        - "本季度" / "本季"
        - "今年以来" / "年初至今"
        - "去年"
        - "最近N天" / "最近N个交易日"

        Args:
            expression: Relative date expression in Chinese.
            reference_date: Reference date (YYYY-MM-DD). Defaults to today.

        Returns:
            Single date string or (start_date, end_date) tuple.
        """
        if reference_date is None:
            today = datetime.now().strftime("%Y-%m-%d")
        else:
            today = reference_date

        expr = expression.strip()

        if expr in ("今天", "今日"):
            return self.get_latest_trading_day(today)

        if expr in ("昨天", "昨日"):
            yesterday = (datetime.strptime(today, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
            return self.get_latest_trading_day(yesterday)

        if expr in ("最近一个交易日", "最新交易日", "最近交易日"):
            return self.get_latest_trading_day(today)

        if expr in ("上个月", "上月"):
            dt = datetime.strptime(today, "%Y-%m-%d")
            # First day of last month
            first_of_this_month = dt.replace(day=1)
            last_of_last_month = first_of_this_month - timedelta(days=1)
            first_of_last_month = last_of_last_month.replace(day=1)
            return (
                self.get_first_trading_day_on_or_after(first_of_last_month.strftime("%Y-%m-%d")),
                self.get_latest_trading_day(last_of_last_month.strftime("%Y-%m-%d")),
            )

        if expr in ("本季度", "本季"):
            dt = datetime.strptime(today, "%Y-%m-%d")
            quarter_start_month = (dt.month - 1) // 3 * 3 + 1
            quarter_start = dt.replace(month=quarter_start_month, day=1)
            return (
                self.get_first_trading_day_on_or_after(quarter_start.strftime("%Y-%m-%d")),
                self.get_latest_trading_day(today),
            )

        if expr in ("今年以来", "年初至今", "YTD"):
            dt = datetime.strptime(today, "%Y-%m-%d")
            year_start = dt.replace(month=1, day=1)
            return (
                self.get_first_trading_day_on_or_after(year_start.strftime("%Y-%m-%d")),
                self.get_latest_trading_day(today),
            )

        if expr == "去年":
            dt = datetime.strptime(today, "%Y-%m-%d")
            last_year = dt.year - 1
            return (
                f"{last_year}-01-01",
                self.get_latest_trading_day(f"{last_year}-12-31"),
            )

        # "最近N天" or "最近N个交易日"
        import re
        match = re.match(r"最近(\d+)个?交易日", expr)
        if match:
            n = int(match.group(1))
            end = self.get_latest_trading_day(today)
            end_dt = datetime.strptime(end, "%Y-%m-%d")
            # Walk back N trading days
            count = 0
            current = end_dt
            while count < n:
                current -= timedelta(days=1)
                if self.is_trading_day(current.strftime("%Y-%m-%d")):
                    count += 1
            return (current.strftime("%Y-%m-%d"), end)

        # Default: try to parse as date
        try:
            datetime.strptime(expr, "%Y-%m-%d")
            return expr
        except ValueError:
            pass

        return today  # Fallback
