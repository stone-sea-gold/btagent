"""Tests for the DuckDB market-data warehouse."""

from datetime import date, datetime, timezone

import pytest

from src.data.schema import AdjustFactor, Bar, Freq, Instrument
from src.data.store import MarketStore


@pytest.fixture
def store(tmp_path):
    with MarketStore(str(tmp_path / "market.duckdb")) as opened:
        yield opened


def _ts(day: str) -> datetime:
    """Naive timestamp — a trading date is a calendar date, not an instant."""
    return datetime.fromisoformat(day)


def bar(day, close=1130.0, volume=1_000_000.0, suspended=False, code="600519.SH", freq=Freq.DAY):
    return Bar(
        freq=freq,
        code=code,
        ts=_ts(day),
        open=close,
        high=close,
        low=close,
        close=close,
        volume=volume,
        amount=volume * close,
        is_suspended=suspended,
        source="test",
    )


class TestSchema:
    def test_tables_are_created(self, store):
        names = {
            row[0]
            for row in store.connect()
            .execute("SELECT table_name FROM information_schema.tables")
            .fetchall()
        }
        assert {"bars", "adjust_factors", "calendar", "instruments", "sync_state"} <= names

    def test_reopening_an_existing_file_is_safe(self, tmp_path):
        path = str(tmp_path / "m.duckdb")
        with MarketStore(path) as first:
            first.upsert_bars([bar("2024-01-02")])
        with MarketStore(path) as second:
            assert len(second.get_bars("600519.SH", date(2024, 1, 1), date(2024, 1, 31))) == 1

    def test_data_directory_is_created(self, tmp_path):
        nested = tmp_path / "a" / "b" / "market.duckdb"
        with MarketStore(str(nested)) as opened:
            opened.upsert_bars([bar("2024-01-02")])
        assert nested.exists()


class TestBars:
    def test_round_trip(self, store):
        store.upsert_bars([bar("2024-01-02", suspended=True, volume=0.0)])

        bars = store.get_bars("600519.SH", date(2024, 1, 1), date(2024, 1, 31))

        assert len(bars) == 1
        stored = bars[0]
        assert stored.code == "600519.SH"
        assert stored.ts == _ts('2024-01-02')
        assert stored.close == 1130.0
        assert stored.is_suspended is True
        assert stored.freq is Freq.DAY

    def test_upsert_is_idempotent(self, store):
        """Running the same sync twice must leave one row, not two."""
        rows = [bar("2024-01-02"), bar("2024-01-03")]

        store.upsert_bars(rows)
        store.upsert_bars(rows)

        assert len(store.get_bars("600519.SH", date(2024, 1, 1), date(2024, 1, 31))) == 2

    def test_upsert_replaces_a_revised_value(self, store):
        store.upsert_bars([bar("2024-01-02", close=100.0)])
        store.upsert_bars([bar("2024-01-02", close=200.0)])

        bars = store.get_bars("600519.SH", date(2024, 1, 1), date(2024, 1, 31))

        assert len(bars) == 1
        assert bars[0].close == 200.0

    def test_range_is_inclusive_and_ordered(self, store):
        store.upsert_bars([bar(d) for d in ("2024-01-02", "2024-01-03", "2024-01-04")])

        bars = store.get_bars("600519.SH", date(2024, 1, 2), date(2024, 1, 3))

        assert [b.ts.date() for b in bars] == [date(2024, 1, 2), date(2024, 1, 3)]

    def test_rows_are_returned_ascending_even_when_written_out_of_order(self, store):
        store.upsert_bars([bar("2024-01-04"), bar("2024-01-02"), bar("2024-01-03")])

        bars = store.get_bars("600519.SH", date(2024, 1, 1), date(2024, 1, 31))

        assert [b.ts.date() for b in bars] == [
            date(2024, 1, 2),
            date(2024, 1, 3),
            date(2024, 1, 4),
        ]

    def test_frequencies_do_not_collide(self, store):
        """Daily and intraday bars share one table, keyed by freq."""
        store.upsert_bars(
            [
                bar("2024-01-02", freq=Freq.DAY),
                bar("2024-01-02", freq=Freq.MIN_5),
            ]
        )

        daily = store.get_bars("600519.SH", date(2024, 1, 1), date(2024, 1, 31), Freq.DAY)
        intraday = store.get_bars(
            "600519.SH", date(2024, 1, 1), date(2024, 1, 31), Freq.MIN_5
        )

        assert len(daily) == 1
        assert len(intraday) == 1

    def test_codes_lists_distinct_symbols(self, store):
        store.upsert_bars(
            [bar("2024-01-02"), bar("2024-01-03"), bar("2024-01-02", code="000001.SZ")]
        )

        assert store.codes() == ["000001.SZ", "600519.SH"]

    def test_empty_write_is_a_no_op(self, store):
        assert store.upsert_bars([]) == 0


class TestFactors:
    def test_round_trip(self, store):
        store.upsert_factors([AdjustFactor(code="600519.SH", ts=date(2024, 1, 2), factor=7.2)])

        factors = store.get_factors("600519.SH", date(2024, 1, 1), date(2024, 1, 31))

        assert len(factors) == 1
        assert factors[0].factor == pytest.approx(7.2)
        assert factors[0].ts == date(2024, 1, 2)

    def test_upsert_is_idempotent(self, store):
        factors = [AdjustFactor(code="600519.SH", ts=date(2024, 1, 2), factor=7.2)]
        store.upsert_factors(factors)
        store.upsert_factors(factors)

        assert len(store.get_factors("600519.SH", date(2024, 1, 1), date(2024, 1, 31))) == 1

    def test_factors_are_stored_at_daily_granularity(self, store):
        """A factor applies to a trading day, so the column is a DATE."""
        store.upsert_factors([AdjustFactor(code="600519.SH", ts=date(2024, 1, 2), factor=7.2)])

        stored = store.get_factors("600519.SH", date(2024, 1, 1), date(2024, 1, 31))[0]

        assert isinstance(stored.ts, date)


class TestCalendarAndInstruments:
    def test_calendar_round_trip(self, store):
        days = [date(2024, 1, 2), date(2024, 1, 3)]
        store.upsert_calendar(Freq.DAY, days)

        assert store.get_calendar(date(2024, 1, 1), date(2024, 1, 31)) == days

    def test_calendar_is_idempotent(self, store):
        days = [date(2024, 1, 2)]
        store.upsert_calendar(Freq.DAY, days)
        store.upsert_calendar(Freq.DAY, days)

        assert len(store.get_calendar(date(2024, 1, 1), date(2024, 1, 31))) == 1

    def test_instrument_round_trip(self, store):
        store.upsert_instruments(
            [
                Instrument(
                    code="600519.SH",
                    name="贵州茅台",
                    start_date=date(2001, 8, 27),
                    end_date=date(2024, 12, 31),
                )
            ]
        )

        row = store.connect().execute("SELECT code, name FROM instruments").fetchone()

        assert row == ("600519.SH", "贵州茅台")


class TestCoverage:
    def test_reports_what_is_held(self, store):
        store.upsert_bars([bar("2024-01-02"), bar("2024-01-03", code="000001.SZ")])
        store.upsert_factors([AdjustFactor(code="600519.SH", ts=date(2024, 1, 2), factor=1.0)])
        store.upsert_calendar(Freq.DAY, [date(2024, 1, 2), date(2024, 1, 3)])

        report = store.coverage()

        assert report["bars"] == 2
        assert report["codes"] == 2
        assert report["first_date"] == date(2024, 1, 2)
        assert report["last_date"] == date(2024, 1, 3)
        assert report["factor_rows"] == 1
        assert report["calendar_days"] == 2

    def test_empty_warehouse_reports_zeroes(self, store):
        report = store.coverage()

        assert report["bars"] == 0
        assert report["first_date"] is None


class TestSyncState:
    def test_unknown_code_has_no_span(self, store):
        assert store.synced_span("600519.SH") is None

    def test_records_and_reads_back(self, store):
        store.record_sync("600519.SH", Freq.DAY, date(2024, 1, 1), date(2024, 12, 31), 242)

        assert store.synced_span("600519.SH") == (date(2024, 1, 1), date(2024, 12, 31))

    def test_recording_again_widens_rather_than_resets(self, store):
        """Adjacent windows must extend coverage, not replace it."""
        store.record_sync("600519.SH", Freq.DAY, date(2024, 1, 1), date(2024, 12, 31), 242)
        store.record_sync("600519.SH", Freq.DAY, date(2025, 1, 1), date(2025, 12, 31), 240)

        assert store.synced_span("600519.SH") == (date(2024, 1, 1), date(2025, 12, 31))

    def test_recording_a_narrower_window_does_not_shrink_coverage(self, store):
        store.record_sync("600519.SH", Freq.DAY, date(2020, 1, 1), date(2024, 12, 31), 1000)
        store.record_sync("600519.SH", Freq.DAY, date(2024, 1, 1), date(2024, 6, 30), 120)

        assert store.synced_span("600519.SH") == (date(2020, 1, 1), date(2024, 12, 31))

    def test_synced_codes(self, store):
        store.record_sync("600519.SH", Freq.DAY, date(2024, 1, 1), date(2024, 12, 31), 1)
        store.record_sync("000001.SZ", Freq.DAY, date(2024, 1, 1), date(2024, 12, 31), 1)

        assert store.synced_codes() == {"600519.SH", "000001.SZ"}

    def test_spans_are_per_frequency(self, store):
        store.record_sync("600519.SH", Freq.DAY, date(2024, 1, 1), date(2024, 12, 31), 1)

        assert store.synced_span("600519.SH", Freq.MIN_5) is None

    def test_updated_at_is_recorded_in_utc(self, store):
        """An audit instant, unlike the exchange dates stored elsewhere."""
        before = datetime.now(timezone.utc).replace(tzinfo=None)
        store.record_sync("600519.SH", Freq.DAY, date(2024, 1, 1), date(2024, 12, 31), 1)

        stamped = store.connect().execute("SELECT updated_at FROM sync_state").fetchone()[0]

        assert before <= stamped <= datetime.now(timezone.utc).replace(tzinfo=None)
