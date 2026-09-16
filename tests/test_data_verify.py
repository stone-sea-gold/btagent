"""Tests for the adjustment verification checks.

The scenarios use the measured 600519 ex-dividend case, and the measured
000001.SZ rebase, so the tests exercise the situations the checks exist for
rather than synthetic arithmetic.
"""

from datetime import date, datetime

import pytest

from src.data.schema import AdjustFactor, Bar
from src.data.store import MarketStore
from src.data.verify import (
    check_against_published_change,
    check_chain_monotonic,
    verify_adjustment,
)


def _ts(day: str) -> datetime:
    """Naive timestamp — a trading day is a calendar date, not an instant."""
    return datetime.fromisoformat(day)


def bar(day, close, *, code="600519.SH", pct_change=None, suspended=False):
    return Bar(
        code=code,
        ts=_ts(day),
        open=close,
        high=close,
        low=close,
        close=close,
        volume=0.0 if suspended else 1_000_000.0,
        amount=0.0 if suspended else close * 1_000_000,
        is_suspended=suspended,
        pct_change=pct_change,
        source="test",
    )


def factor(day, value, *, code="600519.SH"):
    return AdjustFactor(code=code, ts=date.fromisoformat(day), factor=value, source="test")


@pytest.fixture
def store(tmp_path):
    with MarketStore(str(tmp_path / "market.duckdb")) as opened:
        yield opened


def seed_dividend_case(store, *, published=0.001736, code="600519.SH"):
    """600519 across its 2020-06-24 ex-dividend date, with real figures.

    The raw price fell 0.98% while the exchange published +0.1736%; the
    adjusted series reproduces the published figure.
    """
    store.upsert_bars(
        [
            bar("2020-06-23", 1474.50, code=code, pct_change=0.024670),
            bar("2020-06-24", 1460.01, code=code, pct_change=published),
        ]
    )
    store.upsert_factors(
        [factor("2020-06-23", 6.491130, code=code), factor("2020-06-24", 6.566931, code=code)]
    )


class TestAgainstPublishedChange:
    def test_matching_case_passes(self, store):
        seed_dividend_case(store)

        report = check_against_published_change(store)

        assert report.ok
        assert report.published_checked == 1
        assert report.mismatches == []

    def test_the_ex_dividend_day_is_counted(self, store):
        seed_dividend_case(store)

        report = check_against_published_change(store)

        assert report.ex_dividend_days == 1

    def test_a_wrong_published_value_is_caught(self, store):
        """Seeding the raw change as 'published' must fail, not pass quietly."""
        seed_dividend_case(store, published=-0.009827)

        report = check_against_published_change(store)

        assert not report.ok
        assert len(report.mismatches) == 1
        mismatch = report.mismatches[0]
        assert mismatch.day == date(2020, 6, 24)
        assert mismatch.deviation > 0.01, "a 1.16pp gap must be well over tolerance"

    def test_ordinary_days_agree(self, store):
        """No corporate action, so the derived change is just the price move."""
        store.upsert_bars(
            [bar("2020-06-22", 1439.00, pct_change=0.0), bar("2020-06-23", 1474.50, pct_change=0.024670)]
        )
        store.upsert_factors([factor("2020-06-22", 6.491130), factor("2020-06-23", 6.491130)])

        report = check_against_published_change(store)

        assert report.ok
        assert report.ex_dividend_days == 0

    def test_blank_published_values_are_skipped(self, store):
        """A halted day carries no published change; it must not read as zero.

        Two change-days are needed to tell the two behaviours apart: the halted
        day has no value, the next day does.
        """
        store.upsert_bars(
            [
                bar("2020-06-23", 1474.50, pct_change=0.024670),
                bar("2020-06-24", 1460.01, pct_change=None, suspended=True),
                bar("2020-06-29", 1463.17, pct_change=0.002164),
            ]
        )
        store.upsert_factors(
            [
                factor("2020-06-23", 6.566931),
                factor("2020-06-24", 6.566931),
                factor("2020-06-29", 6.566931),
            ]
        )

        report = check_against_published_change(store)

        assert report.ok
        assert report.published_checked == 1, "only the day with a value is compared"

    def test_the_real_rebase_is_caught(self, store):
        """000001.SZ as BaoStock reports it: a -16.82% step with no dividend."""
        store.upsert_bars(
            [
                bar("2020-12-30", 19.20, code="000001.SZ", pct_change=0.001565),
                bar("2020-12-31", 19.34, code="000001.SZ", pct_change=0.007292),
            ]
        )
        store.upsert_factors(
            [
                factor("2020-12-30", 119.960317, code="000001.SZ"),
                factor("2020-12-31", 99.787353, code="000001.SZ"),
            ]
        )

        report = check_against_published_change(store)

        assert not report.ok
        assert report.mismatches[0].deviation > 0.16

    def test_empty_warehouse(self, store):
        report = check_against_published_change(store)

        assert report.ok
        assert report.codes_checked == 0
        assert report.summary()

    def test_code_without_factors_is_skipped(self, store):
        store.upsert_bars([bar("2020-06-23", 1474.50), bar("2020-06-24", 1460.01)])

        report = check_against_published_change(store)

        assert report.skipped == ["600519.SH"]
        assert report.codes_checked == 0


class TestChainMonotonic:
    def test_healthy_chain_passes(self, store):
        store.upsert_factors([factor("2020-05-28", 1.0), factor("2021-05-14", 1.02)])

        report = check_chain_monotonic(store)

        assert report.ok
        assert report.chain_breaks == []

    def test_rebase_is_caught(self, store):
        store.upsert_factors(
            [
                factor("2020-05-28", 119.960317),
                factor("2020-12-31", 99.787353),
            ]
        )

        report = check_chain_monotonic(store)

        assert not report.ok
        assert len(report.chain_breaks) == 1
        assert report.chain_breaks[0].step == pytest.approx(-0.16816, abs=1e-5)

    def test_flat_chain_is_not_a_break(self, store):
        store.upsert_factors([factor("2020-01-01", 5.0), factor("2020-06-01", 5.0)])

        report = check_chain_monotonic(store)

        assert report.ok

    def test_code_without_factors_is_skipped(self, store):
        report = check_chain_monotonic(store)

        assert report.codes_checked == 0


class TestCombined:
    def test_healthy_warehouse_passes_both(self, store):
        seed_dividend_case(store)

        report = verify_adjustment(store)

        assert report.ok
        assert "✅ 通过" in report.summary()

    def test_chain_breaks_surface_through_the_combined_entry_point(self, store):
        store.upsert_factors(
            [factor("2020-05-28", 119.960317), factor("2020-12-31", 99.787353)]
        )

        report = verify_adjustment(store)

        assert not report.ok
        assert report.chain_breaks
        assert "因子链倒退" in report.summary()

    def test_summary_reports_the_worst_deviation(self, store):
        seed_dividend_case(store)

        report = verify_adjustment(store)

        assert "最大偏差" in report.summary()

    def test_mismatch_summary_is_flagged(self, store):
        seed_dividend_case(store, published=-0.009827)

        report = verify_adjustment(store)

        assert "与官方涨跌幅不符" in report.summary()

    def test_window_can_be_restricted(self, store):
        seed_dividend_case(store)

        report = verify_adjustment(store, start=date(2021, 1, 1), end=date(2021, 12, 31))

        assert report.published_checked == 0
