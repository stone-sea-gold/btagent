"""Tests for the provider interface and the fallback chain.

The chain is what implements the project's source strategy, so these tests
pin down the behaviour that makes it safe: the preferred provider always wins,
a failure falls through to the next candidate, and an exhausted chain reports
every provider's error rather than just the last one.
"""

from datetime import date, datetime

import pytest

from src.data.provider import Capability, DataProvider, ProviderChain
from src.data.schema import AdjustFactor, Bar, Freq, Instrument
from src.exceptions import DataSourceError


def _ts(year, month, day, hour=0, minute=0):
    """Naive timestamp — a trading date is a calendar date, not an instant."""
    return datetime(year, month, day, hour, minute)  # noqa: DTZ001


def _bar(code="600519.SH", ts=None, source=""):
    return Bar(
        code=code,
        ts=ts if ts is not None else _ts(2024, 1, 2),
        open=1685.0,
        high=1710.0,
        low=1680.0,
        close=1700.0,
        volume=3_200_000.0,
        amount=5_400_000_000.0,
        source=source,
    )


class FakeProvider(DataProvider):
    """Minimal provider double: records calls and can be made to fail."""

    def __init__(self, name, *, caps=None, freqs=None, fail_with=None, bars=None):
        self.name = name
        self._caps = frozenset(caps if caps is not None else [Capability.BARS])
        self._freqs = frozenset(freqs if freqs is not None else [Freq.DAY])
        self._fail_with = fail_with
        self._bars = bars if bars is not None else [_bar(source=name)]
        self.calls = []

    def capabilities(self):
        return self._caps

    def freqs(self):
        return self._freqs

    def _maybe_fail(self, method):
        self.calls.append(method)
        if self._fail_with is not None:
            raise DataSourceError(f"{self.name} {method} failed", {"provider": self.name})

    def get_bars(self, code, start, end, freq=Freq.DAY):
        self._maybe_fail("get_bars")
        return self._bars

    def get_factors(self, code, start, end):
        self._maybe_fail("get_factors")
        return [AdjustFactor(code=code, ts=start, factor=1.0, source=self.name)]

    def get_calendar(self, start, end, freq=Freq.DAY):
        self._maybe_fail("get_calendar")
        return [_ts(2024, 1, 2)]

    def get_instruments(self, on=None):
        self._maybe_fail("get_instruments")
        return [
            Instrument(
                code="600519.SH", start_date=date(2001, 8, 27), end_date=date(2024, 1, 2)
            )
        ]


class TestCapabilities:
    def test_supports_reports_declared_capabilities(self):
        provider = FakeProvider("a", caps=[Capability.BARS, Capability.CALENDAR])
        assert provider.supports(Capability.BARS)
        assert provider.supports(Capability.CALENDAR)
        assert not provider.supports(Capability.INSTRUMENTS)

    def test_supports_checks_frequency_for_bars(self):
        provider = FakeProvider("a", freqs=[Freq.DAY])
        assert provider.supports(Capability.BARS, Freq.DAY)
        assert not provider.supports(Capability.BARS, Freq.MIN_5)

    def test_frequency_is_ignored_for_non_bar_capabilities(self):
        provider = FakeProvider("a", caps=[Capability.CALENDAR], freqs=[])
        assert provider.supports(Capability.CALENDAR, Freq.MIN_5)

    def test_require_raises_with_actionable_message(self):
        provider = FakeProvider("baostock", freqs=[Freq.DAY])
        with pytest.raises(DataSourceError, match="does not support bars"):
            provider.require(Capability.BARS, Freq.MIN_1)

    def test_require_passes_when_supported(self):
        FakeProvider("a").require(Capability.BARS, Freq.DAY)

    def test_repr_summarizes_declaration(self):
        assert "capabilities=['bars']" in repr(FakeProvider("a"))


class TestProviderChainOrdering:
    def test_preferred_provider_wins(self):
        first = FakeProvider("baostock")
        second = FakeProvider("akshare")
        chain = ProviderChain([first, second])

        bars = chain.get_bars("600519.SH", date(2024, 1, 1), date(2024, 1, 31))

        assert bars[0].source == "baostock"
        assert second.calls == [], "a later provider must not be consulted on success"

    def test_chain_name_lists_providers_in_order(self):
        chain = ProviderChain([FakeProvider("baostock"), FakeProvider("pytdx")])
        assert chain.name == "baostock+pytdx"

    def test_empty_chain_rejected(self):
        with pytest.raises(ValueError, match="at least one provider"):
            ProviderChain([])

    def test_capabilities_are_unioned(self):
        chain = ProviderChain(
            [
                FakeProvider("a", caps=[Capability.BARS], freqs=[Freq.DAY]),
                FakeProvider("b", caps=[Capability.INSTRUMENTS], freqs=[Freq.MIN_5]),
            ]
        )
        assert chain.capabilities() == frozenset({Capability.BARS, Capability.INSTRUMENTS})
        assert chain.freqs() == frozenset({Freq.DAY, Freq.MIN_5})


class TestProviderChainFallback:
    def test_falls_through_on_failure(self):
        broken = FakeProvider("baostock", fail_with="down")
        healthy = FakeProvider("akshare")
        chain = ProviderChain([broken, healthy])

        bars = chain.get_bars("600519.SH", date(2024, 1, 1), date(2024, 1, 31))

        assert bars[0].source == "akshare"
        assert broken.calls == ["get_bars"], "the preferred provider is tried first"
        assert healthy.calls == ["get_bars"]

    def test_skips_provider_that_cannot_serve_request(self):
        daily_only = FakeProvider("baostock", freqs=[Freq.DAY])
        intraday = FakeProvider("pytdx", freqs=[Freq.MIN_5])
        chain = ProviderChain([daily_only, intraday])

        bars = chain.get_bars("600519.SH", date(2024, 1, 1), date(2024, 1, 31), Freq.MIN_5)

        assert bars[0].source == "pytdx"
        assert daily_only.calls == [], "an unsupported frequency must not be attempted"

    def test_exhausted_chain_reports_every_error(self):
        chain = ProviderChain(
            [FakeProvider("baostock", fail_with="x"), FakeProvider("akshare", fail_with="y")]
        )

        with pytest.raises(DataSourceError) as excinfo:
            chain.get_bars("600519.SH", date(2024, 1, 1), date(2024, 1, 31))

        assert set(excinfo.value.details["errors"]) == {"baostock", "akshare"}

    def test_no_capable_provider_is_named(self):
        chain = ProviderChain([FakeProvider("a", caps=[Capability.INSTRUMENTS])])

        with pytest.raises(DataSourceError, match="no provider in chain"):
            chain.get_bars("600519.SH", date(2024, 1, 1), date(2024, 1, 31))


class TestProviderChainDelegation:
    def test_factors_route_to_capable_provider(self):
        no_factors = FakeProvider("baostock", caps=[Capability.BARS])
        with_factors = FakeProvider("akshare", caps=[Capability.BARS, Capability.FACTORS])
        chain = ProviderChain([no_factors, with_factors])

        factors = chain.get_factors("600519.SH", date(2024, 1, 1), date(2024, 1, 31))

        assert factors[0].source == "akshare"
        assert no_factors.calls == []

    def test_calendar_and_instruments_delegate(self):
        provider = FakeProvider(
            "a", caps=[Capability.CALENDAR, Capability.INSTRUMENTS], freqs=[Freq.DAY]
        )
        chain = ProviderChain([provider])

        assert chain.get_calendar(date(2024, 1, 1), date(2024, 1, 31))
        assert chain.get_instruments(date(2024, 1, 2))[0].code == "600519.SH"
