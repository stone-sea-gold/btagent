"""Derive adjusted prices and the daily change series.

The warehouse stores raw prices and adjustment factors separately. This module
recombines them into the shape a backtest needs, and it is the only place that
does so — so the adjustment convention lives in one function rather than being
re-derived (and mis-derived) at each call site.

Why ``$change`` must be computed on adjusted prices
---------------------------------------------------
Qlib judges limit moves from the ``$change`` field::

    limit_buy  = $change >= limit_threshold
    limit_sell = $change <= -limit_threshold

So ``$change`` decides whether an order may be filled at all. Computing it from
raw prices is wrong on every ex-dividend day, because the raw price steps down
by the payout while the previous close does not. Measured on 600519 for
2020-06-24, a dividend of 17.02 CNY on a 1474.50 price::

    date         official pctChg   from adjusted   from raw
    2020-06-24         +0.1736%        +0.1736%    -0.9827%

The adjusted series reproduces the exchange's own figure exactly; the raw series
is off by 1.16 percentage points — the size of the dividend. The divergence
always equals the factor's step, so it scales with the corporate action: a
1-for-1 bonus issue (10送10) halves the price and would read as a -50% move,
which Qlib would treat as a limit-down and refuse to sell into.

Even where the distortion stays below the limit threshold it still corrupts
``$change`` as a feature, since several factors and any change-based analytics
consume it directly.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime

from src.data.schema import AdjustFactor, Bar
from src.exceptions import DataSourceError


@dataclass(frozen=True, slots=True)
class DerivedRow:
    """One trading day of the back-adjusted series, ready for export.

    Prices are back-adjusted (``raw × factor``). ``change`` is ``None`` only on
    the first row, which has no predecessor to measure against.
    """

    ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    factor: float
    change: float | None
    is_suspended: bool

    @property
    def trading_date(self):
        """Trading day this row belongs to, ignoring the time component."""
        return self.ts.date()


def derive_series(
    bars: Sequence[Bar], factors: Sequence[AdjustFactor]
) -> list[DerivedRow]:
    """Combine raw bars with adjustment factors into a back-adjusted series.

    Args:
        bars: Raw (unadjusted) bars for one security, any order.
        factors: Adjustment factors for the same security.

    Returns:
        One :class:`DerivedRow` per input bar, ascending by timestamp.

    Raises:
        DataSourceError: a bar has no factor for its trading day. This is
            raised rather than defaulted, because silently assuming a factor of
            1.0 would leave the price unadjusted for a day and produce a
            plausible-looking but wrong ``change``.
    """
    factor_by_day = {factor.ts: factor.factor for factor in factors}

    rows: list[DerivedRow] = []
    previous_close: float | None = None

    for bar in sorted(bars, key=lambda item: item.ts):
        factor = factor_by_day.get(bar.trading_date)
        if factor is None:
            raise DataSourceError(
                f"no adjustment factor for {bar.code} on {bar.trading_date}; "
                "the factor series must cover every trading day",
                {"code": bar.code, "date": bar.trading_date.isoformat()},
            )

        close = bar.close * factor
        rows.append(
            DerivedRow(
                ts=bar.ts,
                open=bar.open * factor,
                high=bar.high * factor,
                low=bar.low * factor,
                close=close,
                volume=bar.volume,
                factor=factor,
                change=None if previous_close is None else close / previous_close - 1,
                is_suspended=bar.is_suspended,
            )
        )
        previous_close = close

    return rows


@dataclass(frozen=True, slots=True)
class ChainArtifact:
    """A recorded factor step that cannot be a corporate action."""

    day: date
    recorded: float
    """Factor value the source reported on ``day``."""

    corrected: float
    """Value the day was given after the chain was made continuous."""

    @property
    def step(self) -> float:
        """Size of the spurious move, as a fraction. Always negative."""
        return self.recorded / self.corrected - 1


def enforce_monotonic_chain(
    actions: Sequence[tuple[date, float]],
) -> tuple[list[tuple[date, float]], list[ChainArtifact]]:
    """Make a back-adjustment factor chain non-decreasing.

    A back-adjusted factor multiplies historical prices upward at each corporate
    action, so it can never fall. A fall therefore cannot be a corporate action:
    it is a rebase in the source, and it manufactures a single-day return that
    never happened.

    BaoStock does exactly this. For 000001.SZ its ``backAdjustFactor`` runs
    119.960317 on 2020-05-28, drops to 99.787353 on 2020-12-31 — a day with no
    dividend, as ``query_dividend_data`` confirms — then continues to 100.572054
    on 2021-05-14. Its own back-adjusted price series carries the same -16.21%
    discontinuity, so the artifact is in the data rather than in how we apply it.

    It matters because -16.8% exceeds the 9.5% limit threshold: Qlib would read
    the day as limit-down and refuse to sell, and any return-based factor would
    ingest a move that never happened.

    The repair holds the previous value on the artifact date and rescales the
    remainder by the same ratio, so the chain stays continuous and later steps
    keep their true size.

    Args:
        actions: ``(date, factor)`` pairs, ascending by date.

    Returns:
        The corrected chain, and one :class:`ChainArtifact` per repair made.
    """
    corrected: list[tuple[date, float]] = []
    artifacts: list[ChainArtifact] = []
    scale = 1.0

    for day, recorded in actions:
        value = recorded * scale
        if corrected and value < corrected[-1][1]:
            scale *= corrected[-1][1] / value
            artifacts.append(
                ChainArtifact(day=day, recorded=recorded, corrected=corrected[-1][1])
            )
            value = corrected[-1][1]
        corrected.append((day, value))

    return corrected, artifacts
