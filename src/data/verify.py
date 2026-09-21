"""Verification of the adjustment chain.

What makes a check worth running is that it can fail for a reason the code does
not already guarantee. Two qualify here, and one plausible-looking candidate
deliberately does not.

**Against the exchange's published change.**
The warehouse holds two records of the same quantity: the change the exchange
published (``bars.pct_change``) and the change implied by our raw prices times
our adjustment factors. They are produced independently, so a disagreement is
real evidence. This is the check that found BaoStock's rebased factor chain —
a -16.82% single-day step on 000001.SZ that the derived series reproduced
faithfully, and which would have read as a limit-down to Qlib.

**The chain must not step down.**
A back-adjusted factor multiplies historical prices upward at each corporate
action, so it is non-decreasing by construction. A decrease cannot be a
corporate action and must be a rebase.

**What is deliberately not checked.**
Comparing the adjusted change against the raw change adds nothing. Writing them
out, ``(c_t f_t)/(c_{t-1} f_{t-1}) - 1`` against ``c_t/c_{t-1} - 1``, the two are
equal exactly when ``f_t == f_{t-1}`` — and the factor series sits in the same
row, so the comparison can only restate what it was given. It would pass on
every input, including badly wrong ones, which is worse than no check at all
because it buys confidence it has not earned.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date
from itertools import pairwise

from src.data.schema import AdjustFactor, Bar, Freq
from src.data.store import MarketStore
from src.logging import get_logger

logger = get_logger(__name__)

#: Deviation tolerated from the exchange's published change. The published
#: figure is rounded and the factor carries six decimals, so agreement is
#: expected to about five decimals rather than exactly. Measured on Moutai,
#: Shanghai Airport and Ping An across five years, the worst case was 0.0001
#: percentage points.
PUBLISHED_TOLERANCE = 2e-5


@dataclass(frozen=True, slots=True)
class Mismatch:
    """One day where the derived change disagrees with the published one."""

    code: str
    day: date
    derived_change: float
    published_change: float
    factor_step: float
    """Relative move of the factor that day, so a reader can see whether the
    disagreement lines up with a corporate action or is inexplicable."""

    @property
    def deviation(self) -> float:
        """Absolute difference from the published figure."""
        return abs(self.derived_change - self.published_change)


@dataclass(frozen=True, slots=True)
class ChainBreak:
    """One place where a stored factor chain steps down."""

    code: str
    day: date
    previous: float
    current: float

    @property
    def step(self) -> float:
        """Size of the backward step, as a fraction. Always negative."""
        return self.current / self.previous - 1


@dataclass
class AdjustmentReport:
    """Outcome of verifying the adjustment chain."""

    codes_checked: int = 0
    days_checked: int = 0
    ex_dividend_days: int = 0
    published_checked: int = 0
    max_published_deviation: float = 0.0
    mismatches: list[Mismatch] = field(default_factory=list)
    chain_breaks: list[ChainBreak] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    """Codes that could not be checked, with the reason."""

    @property
    def ok(self) -> bool:
        """Whether every check passed."""
        return not self.mismatches and not self.chain_breaks

    def summary(self) -> str:
        """One-line, human-readable outcome."""
        parts = [f"{self.codes_checked} 只 / {self.days_checked:,} 天"]
        if self.published_checked:
            parts.append(
                f"对比官方涨跌幅 {self.published_checked:,} 天"
                f"(最大偏差 {self.max_published_deviation * 100:.4f}pp)"
            )
        if self.mismatches:
            parts.append(f"⚠️ {len(self.mismatches)} 天与官方涨跌幅不符")
        if self.chain_breaks:
            parts.append(f"⚠️ {len(self.chain_breaks)} 处因子链倒退")
        if self.ok:
            parts.append("✅ 通过")
        return " · ".join(parts)


@dataclass(frozen=True, slots=True)
class _DayChange:
    """Derived change for one day, with the factor step that produced it."""

    day: date
    raw_change: float
    adjusted_change: float
    factor_step: float


def _daily_changes(
    bars: Sequence[Bar], factors: Sequence[AdjustFactor]
) -> list[_DayChange]:
    """Derive the back-adjusted change for each consecutive pair of bars."""
    factor_by_day = {factor.ts: factor.factor for factor in factors}
    ordered = sorted(bars, key=lambda bar: bar.ts)

    changes: list[_DayChange] = []
    for previous, current in pairwise(ordered):
        previous_factor = factor_by_day.get(previous.trading_date)
        current_factor = factor_by_day.get(current.trading_date)
        if previous_factor is None or current_factor is None or not previous.close:
            continue

        changes.append(
            _DayChange(
                day=current.trading_date,
                raw_change=current.close / previous.close - 1,
                adjusted_change=(current.close * current_factor)
                / (previous.close * previous_factor)
                - 1,
                factor_step=current_factor / previous_factor - 1,
            )
        )
    return changes


def check_against_published_change(
    store: MarketStore,
    codes: Iterable[str] | None = None,
    start: date | None = None,
    end: date | None = None,
    freq: Freq = Freq.DAY,
    tolerance: float = PUBLISHED_TOLERANCE,
) -> AdjustmentReport:
    """Compare the derived change against the exchange's published figure.

    Args:
        store: Warehouse to inspect.
        codes: Codes to check; defaults to everything at ``freq``.
        start: First day to consider; defaults to the earliest stored.
        end: Last day to consider; defaults to the latest stored.
        freq: Bar frequency.
        tolerance: Largest deviation accepted, as a fraction.

    Returns:
        An :class:`AdjustmentReport`. Days with no published value — halted
        days, and any source that does not supply one — are skipped rather than
        treated as zero, which would fabricate mismatches.
    """
    coverage = store.coverage(freq)
    window_start = start or coverage["first_date"]
    window_end = end or coverage["last_date"]

    report = AdjustmentReport()
    if window_start is None or window_end is None:
        return report

    for code in codes if codes is not None else store.codes(freq):
        bars = store.get_bars(code, window_start, window_end, freq)
        factors = store.get_factors(code, window_start, window_end)
        if not bars or not factors:
            report.skipped.append(code)
            continue

        report.codes_checked += 1
        published = {bar.trading_date: bar.pct_change for bar in bars}

        for change in _daily_changes(bars, factors):
            report.days_checked += 1
            if change.factor_step:
                report.ex_dividend_days += 1

            official = published.get(change.day)
            if official is None:
                continue

            report.published_checked += 1
            deviation = abs(change.adjusted_change - official)
            report.max_published_deviation = max(
                report.max_published_deviation, deviation
            )
            if deviation > tolerance:
                report.mismatches.append(
                    Mismatch(
                        code=code,
                        day=change.day,
                        derived_change=change.adjusted_change,
                        published_change=official,
                        factor_step=change.factor_step,
                    )
                )

    logger.info(
        "published_change_checked",
        codes=report.codes_checked,
        days=report.published_checked,
        mismatches=len(report.mismatches),
        max_deviation=report.max_published_deviation,
    )
    return report


def check_chain_monotonic(
    store: MarketStore,
    codes: Iterable[str] | None = None,
    freq: Freq = Freq.DAY,
) -> AdjustmentReport:
    """Verify that no stored factor chain ever steps down.

    The provider repairs rebases before writing, so a break found here means the
    repair was bypassed or a new artifact shape appeared.

    Args:
        store: Warehouse to inspect.
        codes: Codes to check; defaults to everything at ``freq``.
        freq: Bar frequency, used only to default the code list.

    Returns:
        An :class:`AdjustmentReport` whose ``chain_breaks`` lists every step
        down, scanned across the full stored history rather than a window.
    """
    report = AdjustmentReport()
    # The chain is meaningful on its own, so the code list comes from the factor
    # table rather than from `bars`.
    for code in codes if codes is not None else store.factor_codes():
        factors = store.get_factors(code, date(1990, 1, 1), date(2100, 1, 1))
        if not factors:
            report.skipped.append(code)
            continue

        report.codes_checked += 1
        for previous, current in pairwise(factors):
            if current.factor < previous.factor:
                report.chain_breaks.append(
                    ChainBreak(
                        code=code,
                        day=current.ts,
                        previous=previous.factor,
                        current=current.factor,
                    )
                )

    logger.info(
        "chain_monotonic_checked",
        codes=report.codes_checked,
        breaks=len(report.chain_breaks),
    )
    return report


def verify_adjustment(
    store: MarketStore,
    codes: Iterable[str] | None = None,
    start: date | None = None,
    end: date | None = None,
    freq: Freq = Freq.DAY,
) -> AdjustmentReport:
    """Run both checks and merge them into one report."""
    published = check_against_published_change(store, codes, start, end, freq)
    monotonic = check_chain_monotonic(store, codes, freq)

    published.chain_breaks = monotonic.chain_breaks
    return published
