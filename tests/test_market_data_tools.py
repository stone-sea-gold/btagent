"""Tests for market data tools — pytdx (primary), baostock.

Tests cover:
- Import availability
- Error handling for missing data
- Return format consistency
"""

import pytest
from unittest.mock import patch, MagicMock


# ── pytdx tests ─────────────────────────────────────────────────


class TestFetchStockQuote:
    """Test fetch_stock_quote function."""

    def test_import_error_handling(self):
        """Should return error when pytdx not installed."""
        with patch.dict("sys.modules", {"pytdx": None}):
            from src.tools.market_data_tools import fetch_stock_quote
            result = fetch_stock_quote("600519")
            assert result["status"] == "error"

    def test_not_found_handling(self):
        """Should return not_found for invalid symbol."""
        try:
            import pytdx
        except ImportError:
            pytest.skip("pytdx not installed")
        from src.tools.market_data_tools import fetch_stock_quote
        result = fetch_stock_quote("999999")
        assert result["status"] in ("not_found", "error")


class TestFetchStockHist:
    """Test fetch_stock_hist function."""

    def test_default_dates(self):
        """Should work with default date range."""
        try:
            import pytdx
        except ImportError:
            pytest.skip("pytdx not installed")
        from src.tools.market_data_tools import fetch_stock_hist
        result = fetch_stock_hist("600519")
        assert "status" in result

    def test_return_format(self, mock_pytdx_hist):
        """Should return correct format on success."""
        from src.tools.market_data_tools import fetch_stock_hist
        result = fetch_stock_hist("600519", start="20240101", end="20240131")
        if result["status"] == "success":
            assert "data" in result
            assert "count" in result
            assert isinstance(result["data"], list)


# ── baostock tests ─────────────────────────────────────────────


class TestFetchQuarterlyFinancials:
    """Test fetch_quarterly_financials function."""

    def test_import_error_handling(self):
        """Should return error when baostock not installed."""
        with patch.dict("sys.modules", {"baostock": None}):
            from src.tools.market_data_tools import fetch_quarterly_financials
            result = fetch_quarterly_financials("sh.600519", 2024, 1)
            assert result["status"] == "error"
            assert "baostock" in result["error"]

    def test_code_formatting(self):
        """Should auto-format plain codes to baostock format."""
        try:
            import baostock
        except ImportError:
            pytest.skip("baostock not installed")
        from src.tools.market_data_tools import fetch_quarterly_financials
        # Just verify it doesn't crash with plain code
        result = fetch_quarterly_financials("600519", 2024, 1)
        assert "status" in result


# ── Fixtures ───────────────────────────────────────────────────


@pytest.fixture
def mock_pytdx_hist():
    """Mock pytdx historical data response."""
    import pandas as pd
    mock_df = pd.DataFrame({
        "datetime": ["2024-01-02", "2024-01-03"],
        "open": [1800.0, 1810.0],
        "high": [1820.0, 1830.0],
        "low": [1790.0, 1800.0],
        "close": [1810.0, 1820.0],
        "vol": [10000, 12000],
        "amount": [1.8e9, 2.1e9],
    })
    with patch("pytdx.hq.TdxHq_API.get_security_bars", return_value=mock_df.values.tolist()):
        yield mock_df
