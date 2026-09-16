"""Tests for the BaoStock provider.

The fake module below mirrors the shape the real one returns — ``next()`` /
``get_row_data()`` cursors, every value a string, results carrying
``error_code`` / ``error_msg`` — so these tests exercise the provider's own
logic rather than any network behaviour.

The cases that matter most are the adjustment-factor ones. BaoStock reports a
factor only on ex-dividend dates, and getting the fill wrong silently corrupts
every backtest that follows, in two distinct ways:

* filling backwards from the first in-window action applies a dividend to days
  before it happened (look-ahead bias),
* leaving gaps unfilled makes Qlib disable ``trade_unit``, so orders stop being
  rounded to whole lots.

Both are asserted directly below.

A live check against the real service is included and skipped unless
``AIFUND5_NETWORK_TESTS=1`` is set.
"""

import os
from datetime import date, datetime

import pytest

from src.data.provider import Capability
from src.data.providers.baostock import (
    ADJUST_RAW,
    BaoStockProvider,
    _factor_on,
    _require_float,
    _to_date,
    _to_float,
)
from src.data.schema import Freq
from src.exceptions import DataSourceError

NETWORK = os.environ.get("AIFUND5_NETWORK_TESTS") == "1"


# ── fake BaoStock ──────────────────────────────────────────────────


class FakeResult:
    """Mimics BaoStock's cursor: string rows, drained by next()."""

    def __init__(self, fields, rows, error_code="0", error_msg="success"):
        self.fields = fields
        self.error_code = error_code
        self.error_msg = error_msg
        self._rows = rows
        self._index = -1

    def next(self):
        self._index += 1
        return self._index < len(self._rows)

    def get_row_data(self):
        return self._rows[self._index]


DAILY_FIELDS = [
    "date", "code", "open", "high", "low", "close",
    "preclose", "volume", "amount", "tradestatus", "pctChg", "isST",
]
FACTOR_FIELDS = [
    "code", "dividOperateDate", "foreAdjustFactor", "backAdjustFactor", "adjustFactor",
]


def daily_row(day, close="1130.0000", volume="14809916", amount="16696837095.0000",
              tradestatus="1"):
    return [
        day, "sh.600519", "1128.0000", "1145.0600", "1116.0000", close,
        "1183.0000", volume, amount, tradestatus, "-4.480100", "0",
    ]


def suspended_row(day, preclose="50.4300"):
    """The exact shape BaoStock sent for 600009 on 2022-04-08.

    OHLC collapse onto the previous close, volume and amount are empty strings,
    and tradestatus reads "0".
    """
    return [
        day, "sh.600519", preclose, preclose, preclose, preclose,
        preclose, "", "", "0", "", "0",
    ]


class FakeBaoStock:
    """Stand-in for the baostock module, recording what it was asked for."""

    def __init__(
        self,
        *,
        daily=None,
        factors=None,
        calendar=None,
        stocks=None,
        hs300=None,
        fail_login=False,
        query_error=None,
    ):
        self._daily = daily if daily is not None else []
        self._factors = factors if factors is not None else []
        self._calendar = calendar if calendar is not None else []
        self._stocks = stocks if stocks is not None else []
        self._hs300 = hs300 if hs300 is not None else []
        self._fail_login = fail_login
        self._query_error = query_error
        self.calls = []
        self.logged_in = False
        self.logins = 0

    def login(self):
        self.logins += 1
        if self._fail_login:
            return FakeResult([], [], error_code="10001", error_msg="network down")
        self.logged_in = True
        return FakeResult([], [])

    def logout(self):
        self.logged_in = False
        return FakeResult([], [])

    def query_history_k_data_plus(
        self, code, fields, start_date, end_date, frequency, adjustflag
    ):
        self.calls.append(("history", code, start_date, end_date, frequency, adjustflag))
        if self._query_error:
            return FakeResult(DAILY_FIELDS, [], error_code="9", error_msg=self._query_error)
        return FakeResult(DAILY_FIELDS, self._daily)

    def query_adjust_factor(self, code, start_date, end_date):
        self.calls.append(("adjust_factor", code, start_date, end_date))
        return FakeResult(FACTOR_FIELDS, self._factors)

    def query_trade_dates(self, start_date, end_date):
        self.calls.append(("trade_dates", start_date, end_date))
        return FakeResult(["calendar_date", "is_trading_day"], self._calendar)

    def query_stock_basic(self, code=""):
        self.calls.append(("stock_basic", code))
        return FakeResult(
            ["code", "code_name", "ipoDate", "outDate", "type", "status"], self._stocks
        )

    def query_hs300_stocks(self):
        self.calls.append(("hs300",))
        return FakeResult(["updateDate", "code", "code_name"], self._hs300)


def _ts(year, month, day, hour=0, minute=0):
    """Naive timestamp — a trading date is a calendar date, not an instant."""
    return datetime(year, month, day, hour, minute)  # noqa: DTZ001


def provider_with(fake):
    provider = BaoStockProvider()
    provider._bs = lambda: fake  # type: ignore[method-assign]
    return provider


# ── pure helpers ───────────────────────────────────────────────────


class TestHelpers:
    @pytest.mark.parametrize("text,expected", [("1130.0000", 1130.0), ("0", 0.0)])
    def test_to_float(self, text, expected):
        assert _to_float(text) == expected

    @pytest.mark.parametrize("blank", ["", "   ", None])
    def test_to_float_treats_blanks_as_absent(self, blank):
        assert _to_float(blank) is None

    def test_to_float_rejects_garbage(self):
        with pytest.raises(DataSourceError, match="cannot parse"):
            _to_float("not-a-number")

    def test_require_float_names_the_field(self):
        with pytest.raises(DataSourceError, match="missing required field 'close'"):
            _require_float("", "close", "sh.600519 on 2024-01-02")

    def test_to_date(self):
        assert _to_date("2024-01-02") == date(2024, 1, 2)


class TestFactorFill:
    """The piecewise-constant fill: each day takes the latest prior action."""

    ACTIONS = ((date(2019, 6, 28), 6.49113), (date(2020, 6, 24), 6.566931))

    def test_day_before_any_action_uses_the_base(self):
        assert _factor_on([], date(2020, 1, 2)) == 1.0

    def test_day_uses_the_latest_action_at_or_before_it(self):
        assert _factor_on(self.ACTIONS, date(2020, 1, 2)) == pytest.approx(6.49113)

    def test_day_on_the_action_date_already_uses_the_new_factor(self):
        assert _factor_on(self.ACTIONS, date(2020, 6, 24)) == pytest.approx(6.566931)

    def test_day_after_the_action_keeps_it(self):
        assert _factor_on(self.ACTIONS, date(2024, 12, 31)) == pytest.approx(6.566931)

    def test_future_action_is_never_applied(self):
        """Look-ahead guard: an action dated later must not reach an earlier day."""
        future_only = [(date(2021, 6, 25), 6.628762)]
        assert _factor_on(future_only, date(2020, 1, 2)) == 1.0


# ── declaration ────────────────────────────────────────────────────


class TestDeclaration:
    def test_capabilities(self):
        caps = BaoStockProvider().capabilities()
        assert caps == frozenset({Capability.BARS, Capability.FACTORS, Capability.CALENDAR})
        assert Capability.INSTRUMENTS not in caps

    def test_only_daily_is_declared(self):
        assert BaoStockProvider().freqs() == frozenset({Freq.DAY})

    def test_intraday_is_refused_before_reaching_the_network(self):
        provider = BaoStockProvider()
        with pytest.raises(DataSourceError, match="does not support bars"):
            provider.get_bars("600519", date(2024, 1, 1), date(2024, 1, 31), Freq.MIN_1)

    def test_whole_market_instruments_are_refused_with_guidance(self):
        provider = BaoStockProvider()
        with pytest.raises(DataSourceError, match="get_index_constituents"):
            provider.get_instruments()

    def test_unknown_index_is_named(self):
        provider = provider_with(FakeBaoStock())
        with pytest.raises(DataSourceError, match="unknown index"):
            provider.get_index_constituents("nasdaq")


# ── session ────────────────────────────────────────────────────────


class TestSession:
    def test_login_happens_once_across_queries(self):
        fake = FakeBaoStock(calendar=[["2024-01-02", "1"]])
        provider = provider_with(fake)

        provider.get_calendar(date(2024, 1, 1), date(2024, 1, 31))
        provider.get_calendar(date(2024, 1, 1), date(2024, 1, 31))

        assert fake.logins == 1

    def test_login_failure_is_mapped(self):
        provider = provider_with(FakeBaoStock(fail_login=True))
        with pytest.raises(DataSourceError, match="login failed"):
            provider.get_calendar(date(2024, 1, 1), date(2024, 1, 31))

    def test_context_manager_closes_the_session(self):
        fake = FakeBaoStock(calendar=[["2024-01-02", "1"]])
        provider = provider_with(fake)

        with provider:
            assert fake.logged_in
        assert not fake.logged_in

    def test_close_is_idempotent(self):
        provider = provider_with(FakeBaoStock())
        provider.close()
        provider.close()


# ── bars ───────────────────────────────────────────────────────────


class TestGetBars:
    def test_maps_fields_and_requests_raw_prices(self):
        fake = FakeBaoStock(daily=[daily_row("2024-01-02")])
        provider = provider_with(fake)

        bars = provider.get_bars("600519", date(2024, 1, 1), date(2024, 1, 31))

        assert len(bars) == 1
        bar = bars[0]
        assert bar.code == "600519.SH"
        assert bar.ts == _ts(2024, 1, 2)
        assert (bar.open, bar.high, bar.low, bar.close) == (1128.0, 1145.06, 1116.0, 1130.0)
        assert bar.volume == 14809916.0
        assert bar.amount == 16696837095.0
        assert bar.source == "baostock"

        _, code, start, end, freq, adjustflag = fake.calls[0]
        assert code == "sh.600519"
        assert (start, end) == ("2024-01-01", "2024-01-31")
        assert freq == "d"
        assert adjustflag == ADJUST_RAW, "the warehouse stores raw prices"

    def test_accepts_any_code_spelling(self):
        fake = FakeBaoStock(daily=[daily_row("2024-01-02")])
        provider = provider_with(fake)

        provider.get_bars("SH600519", date(2024, 1, 1), date(2024, 1, 31))

        assert fake.calls[0][1] == "sh.600519"

    def test_rows_without_any_price_are_dropped(self):
        fake = FakeBaoStock(
            daily=[daily_row("2024-01-02"), daily_row("2024-01-03", close="")]
        )
        provider = provider_with(fake)

        bars = provider.get_bars("600519", date(2024, 1, 1), date(2024, 1, 31))

        assert [bar.ts.date() for bar in bars] == [date(2024, 1, 2)]

    def test_suspended_day_is_flagged_with_zero_volume(self):
        """The real 600009 shape: a flat bar with blank volume, flagged halted."""
        fake = FakeBaoStock(
            daily=[daily_row("2022-04-07"), suspended_row("2022-04-08")]
        )
        provider = provider_with(fake)

        bars = provider.get_bars("600009", date(2022, 4, 1), date(2022, 4, 30))

        assert len(bars) == 2, "a halt must not be silently dropped"
        halted = bars[1]
        assert halted.is_suspended is True
        assert halted.volume == 0.0
        assert halted.amount == 0.0
        assert halted.open == halted.close, "a halt is a flat bar"

    def test_blank_volume_on_a_trading_day_still_fails_loudly(self):
        """Only a flagged halt excuses a missing volume."""
        broken = daily_row("2024-01-02", volume="", tradestatus="1")
        provider = provider_with(FakeBaoStock(daily=[broken]))

        with pytest.raises(DataSourceError, match="missing required field 'volume'"):
            provider.get_bars("600519", date(2024, 1, 1), date(2024, 1, 31))

    def test_missing_ohlc_field_fails_loudly(self):
        broken = daily_row("2024-01-02")
        broken[DAILY_FIELDS.index("open")] = ""
        provider = provider_with(FakeBaoStock(daily=[broken]))

        with pytest.raises(DataSourceError, match="missing required field 'open'"):
            provider.get_bars("600519", date(2024, 1, 1), date(2024, 1, 31))

    def test_rows_are_sorted_by_timestamp(self):
        fake = FakeBaoStock(daily=[daily_row("2024-01-04"), daily_row("2024-01-02")])
        provider = provider_with(fake)

        bars = provider.get_bars("600519", date(2024, 1, 1), date(2024, 1, 31))

        assert [bar.ts.date() for bar in bars] == [date(2024, 1, 2), date(2024, 1, 4)]

    def test_query_error_is_mapped(self):
        provider = provider_with(FakeBaoStock(query_error="service busy"))
        with pytest.raises(DataSourceError, match="service busy"):
            provider.get_bars("600519", date(2024, 1, 1), date(2024, 1, 31))


# ── factors ────────────────────────────────────────────────────────


class TestGetFactors:
    def _fake(self, factors, trading_days):
        return FakeBaoStock(
            factors=factors,
            calendar=[[day, "1"] for day in trading_days],
        )

    def test_every_trading_day_gets_a_factor(self):
        """Sparse events must become a dense series, or Qlib disables trade_unit."""
        fake = self._fake(
            factors=[
                ["sh.600519", "2019-06-28", "0.846383", "6.491130", "6.491130"],
                ["sh.600519", "2020-06-24", "0.856267", "6.566931", "6.566931"],
            ],
            trading_days=["2020-01-02", "2020-01-03", "2020-06-24", "2020-06-25"],
        )
        provider = provider_with(fake)

        factors = provider.get_factors("600519", date(2020, 1, 1), date(2020, 12, 31))

        assert len(factors) == 4
        assert all(f.factor is not None for f in factors), "no NaN may survive"
        assert [round(f.factor, 6) for f in factors] == [
            6.491130, 6.491130, 6.566931, 6.566931,
        ]

    def test_uses_back_adjustment_factor_not_the_ambiguous_column(self):
        """600519 on 2023-06-30 really does report a divergent adjustFactor."""
        fake = self._fake(
            factors=[["sh.600519", "2023-06-30", "0.898366", "6.889798", "0.988591"]],
            trading_days=["2023-06-30"],
        )
        provider = provider_with(fake)

        factors = provider.get_factors("600519", date(2023, 1, 1), date(2023, 12, 31))

        assert factors[0].factor == pytest.approx(6.889798)

    def test_history_is_scanned_from_the_epoch(self):
        """Starting at ``start`` would leave the opening days without a factor."""
        fake = self._fake(factors=[], trading_days=["2020-01-02"])
        provider = provider_with(fake)

        provider.get_factors("600519", date(2020, 1, 1), date(2020, 12, 31))

        call = next(c for c in fake.calls if c[0] == "adjust_factor")
        start, end = call[2], call[3]
        assert start.startswith("1990"), f"expected an epoch scan, got {start}"
        assert end == "2020-12-31"

    def test_no_corporate_action_ever_yields_the_base_factor(self):
        fake = self._fake(factors=[], trading_days=["2020-01-02", "2020-01-03"])
        provider = provider_with(fake)

        factors = provider.get_factors("600519", date(2020, 1, 1), date(2020, 12, 31))

        assert [f.factor for f in factors] == [1.0, 1.0]

    def test_calendar_days_off_are_excluded(self):
        fake = self._fake(
            factors=[["sh.600519", "2019-06-28", "0.846383", "6.491130", "6.491130"]],
            trading_days=["2020-01-02"],
        )
        fake._calendar = [["2020-01-02", "1"], ["2020-01-04", "0"]]
        provider = provider_with(fake)

        factors = provider.get_factors("600519", date(2020, 1, 1), date(2020, 12, 31))

        assert [f.ts for f in factors] == [date(2020, 1, 2)]


# ── calendar and constituents ──────────────────────────────────────


class TestCalendarAndConstituents:
    def test_calendar_keeps_only_trading_days(self):
        fake = FakeBaoStock(
            calendar=[["2024-01-01", "0"], ["2024-01-02", "1"], ["2024-01-03", "1"]]
        )
        provider = provider_with(fake)

        days = provider.get_calendar(date(2024, 1, 1), date(2024, 1, 31))

        assert [d.date() for d in days] == [date(2024, 1, 2), date(2024, 1, 3)]

    def test_constituents_are_canonicalized(self):
        fake = FakeBaoStock(
            hs300=[
                ["2024-12-31", "sh.600000", "浦发银行"],
                ["2024-12-31", "sz.000001", "平安银行"],
            ]
        )
        provider = provider_with(fake)

        codes = provider.get_index_constituents("csi300")

        assert codes == ["600000.SH", "000001.SZ"]

    def test_index_aliases_resolve(self):
        for alias in ("csi300", "hs300", "CSI300"):
            fake = FakeBaoStock(hs300=[])
            provider = provider_with(fake)
            provider.get_index_constituents(alias)
            assert ("hs300",) in fake.calls


# ── live service ───────────────────────────────────────────────────


@pytest.mark.skipif(not NETWORK, reason="set AIFUND5_NETWORK_TESTS=1 to hit the live service")
class TestLiveService:
    """End-to-end check against BaoStock, verifying the documented conventions."""

    def test_moutai_history_units_and_factors(self):
        start, end = date(2020, 1, 1), date(2020, 12, 31)

        with BaoStockProvider() as provider:
            bars = provider.get_bars("600519", start, end)
            factors = provider.get_factors("600519", start, end)
            calendar = provider.get_calendar(start, end)

        assert len(bars) == len(calendar), "every trading day should have a bar"

        # Volume is shares: amount / volume must land on the share price, not
        # 100x it as it would if volume were in lots.
        first = bars[0]
        assert 0.9 < (first.amount / first.volume) / first.close < 1.1

        assert len(factors) == len(calendar)
        assert all(f.factor > 0 for f in factors)
        # Moutai pays a dividend every year, so the factor must rise in steps.
        assert factors[0].factor < factors[-1].factor
