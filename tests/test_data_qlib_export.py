"""Tests for the Qlib dataset exporter.

The binary layout has to match Qlib's dump byte-for-byte (float32
little-endian, the calendar offset prepended), and the adjusted-price and
suspension conventions come with requirements of their own, so both are
asserted through raw file reads rather than through our own writer.
"""

from datetime import date, datetime

import numpy as np
import pytest

from src.data.qlib_export import QlibExporter
from src.data.schema import AdjustFactor, Bar
from src.data.store import MarketStore
from src.exceptions import AIFundError


def _ts(day: str) -> datetime:
    """Naive timestamp — a trading day is a calendar date, not an instant."""
    return datetime.fromisoformat(day)


def bar(day, close, *, code="600519.SH", volume=1_000_000.0, suspended=False):
    return Bar(
        code=code,
        ts=_ts(day),
        open=close,
        high=close,
        low=close,
        close=close,
        volume=0.0 if suspended else volume,
        amount=0.0 if suspended else close * volume,
        is_suspended=suspended,
        source="test",
    )


def factor(day, value, *, code="600519.SH"):
    return AdjustFactor(code=code, ts=date.fromisoformat(day), factor=value, source="test")


@pytest.fixture
def store(tmp_path):
    with MarketStore(str(tmp_path / "market.duckdb")) as opened:
        yield opened


def _bin(root, code, field) -> np.ndarray:
    return np.fromfile(root / "features" / code / f"{field}.day.bin", dtype="<f4")


class TestLayout:
    def test_writes_the_expected_tree(self, store, tmp_path):
        store.upsert_bars([bar("2024-01-02", 10.0), bar("2024-01-03", 11.0, code="000001.SZ")])
        store.upsert_factors(
            [factor("2024-01-02", 1.0), factor("2024-01-03", 1.0, code="000001.SZ")]
        )

        root = tmp_path / "qlib"
        counts = QlibExporter(root).export(store)

        assert counts == {"instruments": 2, "features": 2, "days": 2, "fields": 7}
        assert (root / "calendars" / "day.txt").exists()
        assert (root / "instruments" / "all.txt").exists()
        for field in ("open", "high", "low", "close", "volume", "factor", "change"):
            assert (root / "features" / "sh600519" / f"{field}.day.bin").exists()

    def test_calendar_lists_trading_days(self, store, tmp_path):
        store.upsert_bars([bar("2024-01-02", 10.0), bar("2024-01-03", 11.0)])
        store.upsert_factors([factor("2024-01-02", 1.0), factor("2024-01-03", 1.0)])

        QlibExporter(tmp_path / "qlib").export(store)

        days = (tmp_path / "qlib" / "calendars" / "day.txt").read_text().splitlines()
        assert days == ["2024-01-02", "2024-01-03"]

    def test_instruments_use_qlib_spelling_and_bar_span(self, store, tmp_path):
        store.upsert_bars([bar("2020-06-23", 1474.50), bar("2024-12-20", 1520.00)])
        store.upsert_factors([factor("2020-06-23", 6.49113), factor("2024-12-20", 7.224927)])

        QlibExporter(tmp_path / "qlib").export(store)

        lines = (tmp_path / "qlib" / "instruments" / "all.txt").read_text().splitlines()
        assert lines == ["SH600519\t2020-06-23\t2024-12-20"]


class TestBinContents:
    """Raw byte-level checks: the leading offset, the values, their dtype."""

    def test_close_reads_back_as_the_adjusted_price(self, store, tmp_path):
        store.upsert_bars([bar("2024-01-02", 100.0, volume=2_000_000.0)])
        store.upsert_factors([factor("2024-01-02", 1.25)])

        root = tmp_path / "qlib"
        QlibExporter(root).export(store)

        full = _bin(root, "sh600519", "close")
        assert full.dtype == np.float32
        assert full[0] == 0, "the calendar offset comes first"
        assert full[1] == pytest.approx(125.0, abs=1e-2)
        assert len(full) == 2

    def test_change_is_the_adjusted_return(self, store, tmp_path):
        store.upsert_bars([bar("2024-01-02", 100.0), bar("2024-01-03", 110.0)])
        store.upsert_factors([factor("2024-01-02", 1.0), factor("2024-01-03", 1.5)])

        root = tmp_path / "qlib"
        QlibExporter(root).export(store)

        values = _bin(root, "sh600519", "change")[1:]
        assert np.isnan(values[0]), "the first day has no predecessor"
        assert values[1] == pytest.approx(110.0 * 1.5 / 100.0 - 1, abs=1e-5)

    def test_halted_days_render_as_nan(self, store, tmp_path):
        """BaoStock's flat bar would otherwise read as a tradable price to Qlib."""
        store.upsert_bars(
            [
                bar("2024-01-02", 50.43),
                bar("2024-01-03", 50.43, suspended=True),
                bar("2024-01-04", 51.00),
            ]
        )
        store.upsert_factors([factor("2024-01-02", 2.59), factor("2024-01-03", 2.59), factor("2024-01-04", 2.59)])

        root = tmp_path / "qlib"
        QlibExporter(root).export(store)

        close = _bin(root, "sh600519", "close")[1:]
        change = _bin(root, "sh600519", "change")[1:]
        factor_ = _bin(root, "sh600519", "factor")[1:]

        assert np.isnan(close[1]), "a suspended day must be missing"
        assert np.isnan(change[1])
        assert factor_[1] == pytest.approx(2.59, abs=1e-3), "factor keeps its value"


class TestEdges:
    def test_first_bin_element_is_the_calendar_offset(self, store, tmp_path):
        """Qlib locates a security's series by its index in the shared calendar."""
        store.upsert_bars([bar("2024-01-02", 10.0, code="000001.SZ")])
        store.upsert_bars([bar("2024-01-05", 100.0)])
        store.upsert_factors([factor("2024-01-02", 1.0, code="000001.SZ"), factor("2024-01-05", 1.0)])

        QlibExporter(tmp_path / "qlib").export(store)

        offset = _bin(tmp_path / "qlib", "sh600519", "close")[0]
        assert offset == 1, "600519 starts on the second calendar day"

    def test_export_without_data_raises(self, store, tmp_path):

        with pytest.raises(AIFundError):
            QlibExporter(tmp_path / "qlib").export(store)

    def test_codes_can_be_narrowed(self, store, tmp_path):
        store.upsert_bars([bar("2024-01-02", 100.0), bar("2024-01-02", 10.0, code="000001.SZ")])
        store.upsert_factors([factor("2024-01-02", 1.0), factor("2024-01-02", 1.0, code="000001.SZ")])

        counts = QlibExporter(tmp_path / "qlib").export(store, codes=["600519.SH"])

        assert counts["instruments"] == 1
        assert counts["features"] == 1
        assert not (tmp_path / "qlib" / "features" / "sz000001").exists()
