"""Tests for the canonical market-data models."""

from datetime import date, datetime

import pytest
from pydantic import ValidationError

from src.data.schema import AdjustFactor, Bar, Freq, Instrument


def _ts(year, month, day, hour=0, minute=0):
    """Build a naive timestamp.

    A trading timestamp is a calendar date in exchange-local time, not an
    instant, so attaching a timezone would be wrong: two bars on the same
    trading day must compare equal regardless of where the reader sits.
    """
    return datetime(year, month, day, hour, minute)  # noqa: DTZ001


class TestFreq:
    """Frequency values must be usable verbatim as Qlib file-name suffixes."""

    def test_values_match_qlib(self):
        assert Freq.DAY.value == "day"
        assert [f.value for f in Freq if f.is_intraday] == [
            "1min",
            "5min",
            "15min",
            "30min",
            "60min",
        ]

    def test_day_is_not_intraday(self):
        assert not Freq.DAY.is_intraday


class TestBar:
    def _bar(self, **overrides):
        payload = {
            "code": "600519.SH",
            "ts": _ts(2024, 1, 2),
            "open": 1685.0,
            "high": 1710.0,
            "low": 1680.0,
            "close": 1700.0,
            "volume": 3_200_000.0,
            "amount": 5_400_000_000.0,
        }
        payload.update(overrides)
        return Bar(**payload)

    def test_defaults(self):
        bar = self._bar()
        assert bar.freq is Freq.DAY
        assert bar.is_suspended is False
        assert bar.source == ""

    def test_code_is_canonicalized_on_input(self):
        """Any spelling is accepted and stored canonically."""
        assert self._bar(code="sh.600519").code == "600519.SH"
        assert self._bar(code="SH600519").code == "600519.SH"

    def test_trading_date_strips_time(self):
        bar = self._bar(ts=_ts(2024, 1, 2, 15, 0))
        assert bar.trading_date == date(2024, 1, 2)

    def test_negative_volume_rejected(self):
        with pytest.raises(ValidationError):
            self._bar(volume=-1.0)

    def test_non_finite_volume_rejected(self):
        with pytest.raises(ValidationError):
            self._bar(volume=float("nan"))

    def test_unknown_code_rejected(self):
        with pytest.raises(ValidationError):
            self._bar(code="not-a-code")

    def test_intraday_bar_keeps_its_timestamp(self):
        bar = self._bar(freq=Freq.MIN_5, ts=_ts(2024, 1, 2, 9, 35))
        assert bar.freq is Freq.MIN_5
        assert bar.trading_date == date(2024, 1, 2)


class TestAdjustFactor:
    def test_holds_back_adjustment_ratio(self):
        factor = AdjustFactor(code="600519.SH", ts=date(2024, 1, 2), factor=1.7)
        assert factor.factor == 1.7

    def test_code_is_canonicalized(self):
        assert AdjustFactor(code="600519", ts=date(2024, 1, 2), factor=1.0).code == "600519.SH"

    @pytest.mark.parametrize("bad", [0.0, -1.0])
    def test_non_positive_factor_rejected(self, bad):
        """A factor of zero would make every adjusted price zero."""
        with pytest.raises(ValidationError):
            AdjustFactor(code="600519.SH", ts=date(2024, 1, 2), factor=bad)


class TestInstrument:
    def test_listing_span(self):
        inst = Instrument(
            code="600519.SH", name="贵州茅台", start_date=date(2001, 8, 27), end_date=date(2024, 1, 2)
        )
        assert inst.name == "贵州茅台"
        assert inst.start_date < inst.end_date

    def test_end_before_start_rejected(self):
        with pytest.raises(ValidationError):
            Instrument(
                code="600519.SH",
                start_date=date(2024, 1, 2),
                end_date=date(2001, 8, 27),
            )

    def test_code_is_canonicalized(self):
        inst = Instrument(code="sz000001", start_date=date(1991, 4, 3), end_date=date(2024, 1, 2))
        assert inst.code == "000001.SZ"
