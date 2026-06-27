"""Tests for TradingCalendar."""

import pytest

from src.core.trading_calendar import TradingCalendar


class TestTradingCalendar:
    """Test trading calendar functionality."""

    def test_is_trading_day_weekday(self, cal):
        assert cal.is_trading_day("2024-01-02") is True  # Tuesday

    def test_is_trading_day_weekend(self, cal):
        assert cal.is_trading_day("2024-01-06") is False  # Saturday
        assert cal.is_trading_day("2024-01-07") is False  # Sunday

    def test_is_trading_day_holiday(self, cal):
        assert cal.is_trading_day("2024-01-01") is False  # New Year

    def test_get_latest_trading_day(self, cal):
        # 2024-01-01 is holiday, should return 2023-12-29 (Friday)
        result = cal.get_latest_trading_day("2024-01-01")
        assert result == "2023-12-29"

    def test_get_latest_trading_day_trading_day(self, cal):
        # 2024-01-02 is a trading day
        result = cal.get_latest_trading_day("2024-01-02")
        assert result == "2024-01-02"

    def test_get_latest_trading_day_weekend(self, cal):
        # 2024-01-06 is Saturday, should return 2024-01-05 (Friday)
        result = cal.get_latest_trading_day("2024-01-06")
        assert result == "2024-01-05"

    def test_get_next_trading_day(self, cal):
        # 2024-01-05 is Friday, next trading day is 2024-01-08 (Monday)
        result = cal.get_next_trading_day("2024-01-05")
        assert result == "2024-01-08"

    def test_get_trading_days(self, cal):
        # One week: 2024-01-02 (Tue) to 2024-01-08 (Mon)
        days = cal.get_trading_days("2024-01-02", "2024-01-08")
        assert len(days) == 5  # Tue, Wed, Thu, Fri, Mon
        assert "2024-01-06" not in days  # Saturday excluded
        assert "2024-01-07" not in days  # Sunday excluded

    def test_parse_relative_date_today(self, cal):
        result = cal.parse_relative_date("今天", "2024-01-15")
        assert result == "2024-01-15"  # Monday

    def test_parse_relative_date_yesterday(self, cal):
        result = cal.parse_relative_date("昨天", "2024-01-15")
        assert result == "2024-01-12"  # Friday (skip weekend)

    def test_parse_relative_date_latest_trading_day(self, cal):
        result = cal.parse_relative_date("最近一个交易日", "2024-01-15")
        assert result == "2024-01-15"

    def test_parse_relative_date_last_month(self, cal):
        result = cal.parse_relative_date("上个月", "2024-02-15")
        assert isinstance(result, tuple)
        assert result[0].startswith("2024-01")
        assert result[1].startswith("2024-01")

    def test_parse_relative_date_ytd(self, cal):
        result = cal.parse_relative_date("今年以来", "2024-03-15")
        assert isinstance(result, tuple)
        assert result[0] == "2024-01-02"  # First trading day of 2024
        assert result[1] == "2024-03-15"

    def test_parse_relative_date_last_n_days(self, cal):
        result = cal.parse_relative_date("最近5个交易日", "2024-01-15")
        assert isinstance(result, tuple)
        assert result[1] == "2024-01-15"


@pytest.fixture
def cal():
    return TradingCalendar()
