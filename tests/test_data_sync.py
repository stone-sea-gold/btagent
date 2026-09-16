"""Tests for the sync layer.

The behaviours worth pinning down are the ones that make a long sync safe to
re-run: resume actually skips, a wider window re-fetches, and one bad symbol
does not abandon the codes already fetched.
"""

from datetime import date, datetime

import pytest

from src.data.provider import Capability, DataProvider
from src.data.schema import AdjustFactor, Bar, Freq
from src.data.store import MarketStore
from src.data.sync import (
    DEV_CODES,
    SyncResult,
    resolve_codes,
    sync_calendar,
    sync_codes,
    sync_universe,
)
from src.exceptions import DataSourceError


def _ts(day: str) -> datetime:
    """Naive timestamp — a trading day is a calendar date, not an instant."""
    return datetime.fromisoformat(day)


class FakeProvider(DataProvider):
    """Provider double that serves a fixed set of codes and counts its calls."""

    name = "fake"

    def __init__(self, data=None, *, fail_for=(), supports_factors=True, calendar=None):
        self._data = data if data is not None else {"600519.SH": ["2024-01-02", "2024-01-03"]}
        self._fail_for = set(fail_for)
        self._supports_factors = supports_factors
        self._calendar = calendar if calendar is not None else ["2024-01-02", "2024-01-03"]
        self.bar_calls: list[str] = []
        self.factor_calls: list[str] = []

    def capabilities(self):
        caps = {Capability.BARS, Capability.CALENDAR}
        if self._supports_factors:
            caps.add(Capability.FACTORS)
        return frozenset(caps)

    def freqs(self):
        return frozenset({Freq.DAY})

    def get_bars(self, code, start, end, freq=Freq.DAY):
        self.bar_calls.append(code)
        if code in self._fail_for:
            raise DataSourceError(f"{code} unavailable")
        return [
            Bar(
                code=code,
                ts=_ts(day),
                open=10.0,
                high=10.0,
                low=10.0,
                close=10.0,
                volume=100.0,
                amount=1000.0,
                source=self.name,
            )
            for day in self._data.get(code, [])
        ]

    def get_factors(self, code, start, end):
        self.factor_calls.append(code)
        if code in self._fail_for:
            raise DataSourceError(f"{code} unavailable")
        return [
            AdjustFactor(code=code, ts=date(2024, 1, 2), factor=1.5, source=self.name)
        ]

    def get_calendar(self, start, end, freq=Freq.DAY):
        return [_ts(day) for day in self._calendar]

    def get_instruments(self, on=None):
        return []

    def get_index_constituents(self, index):
        if index != "csi300":
            raise DataSourceError(f"unknown index {index!r}")
        return ["600519.SH", "000001.SZ"]


@pytest.fixture
def store(tmp_path):
    with MarketStore(str(tmp_path / "market.duckdb")) as opened:
        yield opened


WINDOW = (date(2024, 1, 1), date(2024, 12, 31))


class TestSyncCodes:
    def test_writes_bars_and_factors(self, store):
        provider = FakeProvider()

        result = sync_codes(store, provider, ["600519.SH"], *WINDOW)

        assert result.codes_synced == 1
        assert result.bars_written == 2
        assert result.factors_written == 1
        assert len(store.get_bars("600519.SH", *WINDOW)) == 2
        assert len(store.get_factors("600519.SH", *WINDOW)) == 1

    def test_records_the_synced_span(self, store):
        sync_codes(store, FakeProvider(), ["600519.SH"], *WINDOW)

        assert store.synced_span("600519.SH") == WINDOW

    def test_skips_factors_when_provider_has_none(self, store):
        provider = FakeProvider(supports_factors=False)

        result = sync_codes(store, provider, ["600519.SH"], *WINDOW)

        assert result.factors_written == 0
        assert provider.factor_calls == []

    def test_empty_code_list_is_harmless(self, store):
        result = sync_codes(store, FakeProvider(), [], *WINDOW)

        assert result.codes_requested == 0
        assert result.ok


class TestResume:
    def test_rerun_skips_covered_codes(self, store):
        provider = FakeProvider()
        sync_codes(store, provider, ["600519.SH"], *WINDOW)
        provider.bar_calls.clear()

        result = sync_codes(store, provider, ["600519.SH"], *WINDOW)

        assert result.codes_skipped == 1
        assert result.codes_synced == 0
        assert provider.bar_calls == [], "a covered code must not be re-fetched"

    def test_rerun_is_idempotent_in_the_warehouse(self, store):
        provider = FakeProvider()
        sync_codes(store, provider, ["600519.SH"], *WINDOW)
        sync_codes(store, provider, ["600519.SH"], *WINDOW)

        assert len(store.get_bars("600519.SH", *WINDOW)) == 2

    def test_resume_disabled_forces_a_refetch(self, store):
        provider = FakeProvider()
        sync_codes(store, provider, ["600519.SH"], *WINDOW)

        result = sync_codes(store, provider, ["600519.SH"], *WINDOW, resume=False)

        assert result.codes_synced == 1
        assert provider.bar_calls.count("600519.SH") == 2

    def test_a_wider_window_refetches(self, store):
        """Extending the window must fetch, not be mistaken for coverage."""
        provider = FakeProvider()
        sync_codes(store, provider, ["600519.SH"], date(2024, 1, 1), date(2024, 6, 30))

        result = sync_codes(store, provider, ["600519.SH"], *WINDOW)

        assert result.codes_synced == 1
        assert store.synced_span("600519.SH") == WINDOW

    def test_a_narrower_window_is_covered_and_skipped(self, store):
        provider = FakeProvider()
        sync_codes(store, provider, ["600519.SH"], *WINDOW)
        provider.bar_calls.clear()

        result = sync_codes(store, provider, ["600519.SH"], date(2024, 3, 1), date(2024, 6, 30))

        assert result.codes_skipped == 1
        assert provider.bar_calls == []

    def test_resume_completes_a_partial_run(self, store):
        """A run interrupted after one code resumes with only the remainder."""
        provider = FakeProvider(
            {"600519.SH": ["2024-01-02"], "000001.SZ": ["2024-01-02"]}
        )
        sync_codes(store, provider, ["600519.SH"], *WINDOW)
        provider.bar_calls.clear()

        result = sync_codes(store, provider, ["600519.SH", "000001.SZ"], *WINDOW)

        assert result.codes_skipped == 1
        assert result.codes_synced == 1
        assert provider.bar_calls == ["000001.SZ"]


class TestFailureIsolation:
    def test_one_bad_code_does_not_abandon_the_rest(self, store):
        provider = FakeProvider(
            {"600519.SH": ["2024-01-02"], "000001.SZ": ["2024-01-02"]},
            fail_for=["600009.SH"],
        )

        result = sync_codes(
            store, provider, ["600519.SH", "600009.SH", "000001.SZ"], *WINDOW
        )

        assert result.codes_synced == 2
        assert result.codes_failed == 1
        assert "600009.SH" in result.failures
        assert not result.ok
        assert len(store.codes()) == 2

    def test_failures_are_reported_in_the_summary(self, store):
        provider = FakeProvider(fail_for=["600519.SH"])

        result = sync_codes(store, provider, ["600519.SH"], *WINDOW)

        assert "失败" in result.summary()

    def test_a_failed_code_is_retried_next_run(self, store):
        """A failure must not be recorded as coverage."""
        provider = FakeProvider(fail_for=["600519.SH"])
        sync_codes(store, provider, ["600519.SH"], *WINDOW)

        assert store.synced_span("600519.SH") is None

        provider._fail_for.clear()
        result = sync_codes(store, provider, ["600519.SH"], *WINDOW)
        assert result.codes_synced == 1


class TestProgress:
    def test_reports_every_code(self, store):
        seen = []
        provider = FakeProvider({"600519.SH": ["2024-01-02"], "000001.SZ": ["2024-01-02"]})

        sync_codes(
            store,
            provider,
            ["600519.SH", "000001.SZ"],
            *WINDOW,
            progress=lambda done, total, code, rows: seen.append((done, total, code, rows)),
        )

        assert seen == [(1, 2, "600519.SH", 1), (2, 2, "000001.SZ", 1)]

    def test_skipped_codes_are_reported_with_zero_rows(self, store):
        seen = []
        provider = FakeProvider()
        sync_codes(store, provider, ["600519.SH"], *WINDOW)
        sync_codes(
            store,
            provider,
            ["600519.SH"],
            *WINDOW,
            progress=lambda done, total, code, rows: seen.append((code, rows)),
        )

        assert seen == [("600519.SH", 0)]


class TestResolveCodes:
    def test_explicit_codes(self):
        assert resolve_codes(FakeProvider(), codes=["600519.SH"]) == ["600519.SH"]

    def test_index_constituents(self):
        assert resolve_codes(FakeProvider(), index="csi300") == ["600519.SH", "000001.SZ"]

    def test_explicit_codes_win_over_index(self):
        assert resolve_codes(FakeProvider(), index="csi300", codes=["000001.SZ"]) == [
            "000001.SZ"
        ]

    def test_duplicates_are_collapsed_preserving_order(self):
        codes = ["000001.SZ", "600519.SH", "000001.SZ"]
        assert resolve_codes(FakeProvider(), codes=codes) == ["000001.SZ", "600519.SH"]

    def test_neither_given_is_an_error(self):
        with pytest.raises(DataSourceError, match="either index or codes"):
            resolve_codes(FakeProvider())

    def test_provider_without_index_support_is_named(self):
        class NoIndex(FakeProvider):
            get_index_constituents = None

        with pytest.raises(DataSourceError, match="cannot resolve index"):
            resolve_codes(NoIndex(), index="csi300")


class TestSyncCalendar:
    def test_writes_trading_days(self, store):
        written = sync_calendar(store, FakeProvider(), *WINDOW)

        assert written == 2
        assert store.get_calendar(*WINDOW) == [date(2024, 1, 2), date(2024, 1, 3)]

    def test_is_idempotent(self, store):
        sync_calendar(store, FakeProvider(), *WINDOW)
        sync_calendar(store, FakeProvider(), *WINDOW)

        assert len(store.get_calendar(*WINDOW)) == 2


class TestSyncUniverse:
    def test_resolves_and_syncs_an_index(self, store):
        provider = FakeProvider({"600519.SH": ["2024-01-02"], "000001.SZ": ["2024-01-02"]})

        result = sync_universe(store, provider, *WINDOW, index="csi300")

        assert result.codes_requested == 2
        assert result.codes_synced == 2
        assert result.calendar_days == 2
        assert set(store.codes()) == {"600519.SH", "000001.SZ"}


class TestSyncResult:
    def test_ok_when_nothing_failed(self):
        assert SyncResult(codes_synced=3).ok

    def test_summary_mentions_skips_and_failures(self):
        result = SyncResult(codes_synced=1, codes_skipped=2, codes_failed=1, bars_written=10)

        text = result.summary()

        assert "已同步" in text
        assert "跳过" in text
        assert "失败" in text


class TestDevSample:
    def test_dev_codes_cover_the_awkward_cases(self):
        """The dev sample exists to exercise dividends and halts, not to be typical.

        600519 pays an annual dividend, so the adjustment chain advances;
        600009 halted on 2022-04-08, so the suspension path runs. A sample that
        omitted the latter is how the suspension bug stayed hidden.
        """
        assert "600519.SH" in DEV_CODES, "needs a dividend payer"
        assert "600009.SH" in DEV_CODES, "needs a stock that has halted"
        assert all(c.endswith((".SH", ".SZ")) for c in DEV_CODES)
