"""Data provider interface.

A provider adapts one external source (BaoStock, pytdx, AKShare, …) to the
canonical models in :mod:`src.data.schema`. Everything source-specific — URL
building, code spellings, field names, unit quirks, retry policy — stays
inside the subclass.

Two invariants hold for every implementation and are what make the sources
composable:

1. **Bars are unadjusted.** :meth:`DataProvider.get_bars` returns raw traded
   prices. A provider that only publishes adjusted prices must undo the
   adjustment before returning, because otherwise its rows cannot be compared
   against any other source.
2. **Volume is in shares and amount is in CNY.** See :mod:`src.data.schema`.

Providers declare what they can serve through :meth:`capabilities` and
:meth:`freqs`, so callers can pick a source instead of discovering a gap at
runtime.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable, Sequence
from datetime import date, datetime
from enum import Enum
from typing import ClassVar

from src.data.schema import AdjustFactor, Bar, Freq, Instrument
from src.exceptions import DataSourceError


class Capability(str, Enum):
    """A kind of data a provider is able to serve."""

    BARS = "bars"
    """Daily or intraday OHLCV."""

    FACTORS = "factors"
    """Back-adjustment factors. Many sources publish adjusted prices only and
    therefore cannot serve this directly."""

    CALENDAR = "calendar"
    """Trading calendar."""

    INSTRUMENTS = "instruments"
    """Listed security universe with listing/delisting dates."""


class DataProvider(ABC):
    """Base class for a market-data source."""

    name: ClassVar[str] = ""
    """Short provider identifier, stored on every row this provider emits."""

    # ── capability declaration ─────────────────────────────────────

    @abstractmethod
    def capabilities(self) -> frozenset[Capability]:
        """Kinds of data this provider can serve."""

    @abstractmethod
    def freqs(self) -> frozenset[Freq]:
        """Bar frequencies this provider can serve.

        Return an empty set when the provider serves no bars at all.
        """

    def supports(self, capability: Capability, freq: Freq | None = None) -> bool:
        """Whether this provider can serve ``capability``, optionally at ``freq``."""
        if capability not in self.capabilities():
            return False
        if freq is not None and capability is Capability.BARS:
            return freq in self.freqs()
        return True

    def require(self, capability: Capability, freq: Freq | None = None) -> None:
        """Raise unless this provider supports ``capability``.

        Raises:
            DataSourceError: the provider cannot serve the request.
        """
        if not self.supports(capability, freq):
            detail = f" at frequency {freq.value}" if freq is not None else ""
            raise DataSourceError(
                f"provider {self.name!r} does not support {capability.value}{detail}",
                {"provider": self.name, "capability": capability.value},
            )

    # ── data access ────────────────────────────────────────────────

    @abstractmethod
    def get_bars(
        self,
        code: str,
        start: date,
        end: date,
        freq: Freq = Freq.DAY,
    ) -> list[Bar]:
        """Fetch bars for one security over ``[start, end]`` inclusive.

        Implementations must return **unadjusted** prices with volume in shares
        and amount in CNY, sorted by timestamp ascending.

        Args:
            code: Security code in any spelling accepted by
                :func:`src.data.codes.parse`.
            start: First trading day to include.
            end: Last trading day to include.
            freq: Bar frequency.

        Returns:
            Bars in ascending timestamp order; empty when the security did not
            trade in the window.
        """

    @abstractmethod
    def get_factors(self, code: str, start: date, end: date) -> list[AdjustFactor]:
        """Fetch daily back-adjustment factors over ``[start, end]`` inclusive.

        Implementations whose source publishes adjusted prices only must
        recover the factor by dividing the adjusted close by the raw close.
        """

    @abstractmethod
    def get_calendar(self, start: date, end: date, freq: Freq = Freq.DAY) -> list[datetime]:
        """Fetch the trading calendar over ``[start, end]`` inclusive."""

    @abstractmethod
    def get_instruments(self, on: date | None = None) -> list[Instrument]:
        """List securities known to the provider.

        Args:
            on: When given, restrict to securities trading on that date.
                When ``None``, return the full universe including delisted
                names, each carrying its own listing span.
        """

    def __repr__(self) -> str:
        return (
            f"{type(self).__name__}(name={self.name!r}, "
            f"capabilities={sorted(c.value for c in self.capabilities())})"
        )


class ProviderChain(DataProvider):
    """Tries providers in order and falls back on failure.

    The order is a priority list: the first provider is the preferred source
    for every request, and later ones are consulted only when an earlier one
    cannot serve the request or raises :class:`DataSourceError`.

    This implements the project's source strategy — the most stable source
    leads, a bulk-capable source absorbs volume, and a broad-coverage source
    catches the rest — without any provider needing to know about the others.
    """

    def __init__(self, providers: Sequence[DataProvider]) -> None:
        if not providers:
            raise ValueError("ProviderChain requires at least one provider")
        self._providers = tuple(providers)
        self.name = "+".join(p.name for p in self._providers)

    @property
    def providers(self) -> tuple[DataProvider, ...]:
        """The providers in priority order."""
        return self._providers

    def capabilities(self) -> frozenset[Capability]:
        return frozenset().union(*(p.capabilities() for p in self._providers))

    def freqs(self) -> frozenset[Freq]:
        return frozenset().union(*(p.freqs() for p in self._providers))

    def _candidates(
        self, capability: Capability, freq: Freq | None = None
    ) -> Iterable[DataProvider]:
        return [p for p in self._providers if p.supports(capability, freq)]

    def _first(self, capability: Capability, freq: Freq | None, call) -> object:
        """Run ``call`` against the first provider that succeeds."""
        candidates = list(self._candidates(capability, freq))
        if not candidates:
            raise DataSourceError(
                f"no provider in chain {self.name!r} supports {capability.value}",
                {"chain": self.name, "capability": capability.value},
            )
        errors: dict[str, str] = {}
        for provider in candidates:
            try:
                return call(provider)
            except DataSourceError as exc:
                errors[provider.name] = exc.message
        raise DataSourceError(
            f"every provider in chain {self.name!r} failed for {capability.value}",
            {"chain": self.name, "capability": capability.value, "errors": errors},
        )

    def get_bars(self, code: str, start: date, end: date, freq: Freq = Freq.DAY) -> list[Bar]:
        return self._first(  # type: ignore[return-value]
            Capability.BARS, freq, lambda p: p.get_bars(code, start, end, freq)
        )

    def get_factors(self, code: str, start: date, end: date) -> list[AdjustFactor]:
        return self._first(  # type: ignore[return-value]
            Capability.FACTORS, None, lambda p: p.get_factors(code, start, end)
        )

    def get_calendar(self, start: date, end: date, freq: Freq = Freq.DAY) -> list[datetime]:
        return self._first(  # type: ignore[return-value]
            Capability.CALENDAR, freq, lambda p: p.get_calendar(start, end, freq)
        )

    def get_instruments(self, on: date | None = None) -> list[Instrument]:
        return self._first(  # type: ignore[return-value]
            Capability.INSTRUMENTS, None, lambda p: p.get_instruments(on)
        )
