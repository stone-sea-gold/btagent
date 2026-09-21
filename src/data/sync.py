"""Manual market-data sync: provider → warehouse.

Sync is driven explicitly rather than lazily, because pulling a universe is a
deliberate, visible operation: it takes minutes, it hits an external service,
and downstream results are only reproducible if the warehouse contents are
known. Nothing here runs on import or on a timer.

Resume
------
Each code's fetched span is recorded in ``sync_state``. A re-run skips codes
already covering the requested window and fetches only the gaps, so an
interrupted sync is completed by running the same command again. Widening the
window later extends coverage instead of replacing it.

Choosing how much data to pull
------------------------------
Cost is driven mostly by the number of codes, and different data volumes expose
different classes of defect:

* **breadth** (more codes) surfaces per-security quirks — halts, limit moves,
  first-day listings;
* **depth** (more years) surfaces time-series problems — the adjustment chain,
  ex-dividend handling, shifts in market regime.

Real measurements against BaoStock: one code over one year takes ~0.2s, over
five years ~2.6s, and ten codes over five years ~0.6s each. A CSI 300 sync is
therefore roughly 3 minutes for one year and 10 minutes for five.

:data:`DEV_CODES` is the small sample used while developing. It is not an
arbitrary slice — it deliberately includes 600519, which pays an annual
dividend, and 600009, which halted on 2022-04-08 and therefore exercises the
suspension path. A sample of one year taken from 2024 alone contains no halt at
all, which is exactly how the suspension bug in the provider stayed hidden until
a wider pull was attempted.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date
from time import monotonic

from src.data.provider import Capability, DataProvider
from src.data.schema import Freq
from src.data.store import MarketStore
from src.exceptions import DataSourceError
from src.logging import get_logger

logger = get_logger(__name__)

#: Codes used for development and smoke tests. Chosen to cover the awkward
#: cases rather than to be representative: 600519 pays an annual dividend (so
#: the adjustment chain advances), 600009 halted on 2022-04-08 (so the
#: suspension path runs), and 000001 is a Shenzhen main-board name.
DEV_CODES: tuple[str, ...] = ("600519.SH", "600009.SH", "000001.SZ")

#: Default window for a development sync — one year keeps the loop fast.
DEFAULT_YEARS = 1

#: Emitted after each code: (done, total, code, rows_written).
ProgressFn = Callable[[int, int, str, int], None]


@dataclass
class SyncResult:
    """Outcome of one sync run."""

    codes_requested: int = 0
    codes_synced: int = 0
    codes_skipped: int = 0
    codes_failed: int = 0
    bars_written: int = 0
    factors_written: int = 0
    calendar_days: int = 0
    elapsed_seconds: float = 0.0
    failures: dict[str, str] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        """Whether every requested code was synced or skipped."""
        return self.codes_failed == 0

    def summary(self) -> str:
        """One-line, human-readable outcome."""
        parts = [
            f"{self.codes_synced} 只已同步",
            f"{self.bars_written:,} 根 bar",
            f"{self.factors_written:,} 行复权因子",
        ]
        if self.codes_skipped:
            parts.append(f"{self.codes_skipped} 只已存在跳过")
        if self.codes_failed:
            parts.append(f"⚠️ {self.codes_failed} 只失败")
        parts.append(f"{self.elapsed_seconds:.1f}s")
        return " · ".join(parts)


def sync_calendar(
    store: MarketStore,
    provider: DataProvider,
    start: date,
    end: date,
    freq: Freq = Freq.DAY,
) -> int:
    """Fetch and store the trading calendar.

    Stored separately from bars because the calendar is what turns a *missing*
    bar into a meaningful fact: a day in the calendar with no bar is a halt,
    whereas a day absent from the calendar is simply not a trading day.
    """
    days = [tick.date() for tick in provider.get_calendar(start, end, freq)]
    written = store.upsert_calendar(freq, days)
    logger.info("sync_calendar_done", freq=freq.value, days=written)
    return written


def sync_codes(
    store: MarketStore,
    provider: DataProvider,
    codes: Sequence[str],
    start: date,
    end: date,
    *,
    freq: Freq = Freq.DAY,
    resume: bool = True,
    with_factors: bool = True,
    progress: ProgressFn | None = None,
) -> SyncResult:
    """Sync bars (and adjustment factors) for ``codes`` into ``store``.

    Args:
        store: Destination warehouse.
        provider: Source to read from.
        codes: Securities to sync.
        start: First day of the requested window.
        end: Last day of the requested window.
        freq: Bar frequency.
        resume: Skip codes whose recorded span already covers the window.
        with_factors: Also fetch adjustment factors for each code.
        progress: Optional per-code callback.

    Returns:
        A :class:`SyncResult`. Per-code failures are collected rather than
        raised, so one bad symbol cannot abandon a long run.
    """
    result = SyncResult(codes_requested=len(codes))
    started = monotonic()

    for index, code in enumerate(codes, start=1):
        if resume and _already_covered(store, code, freq, start, end):
            result.codes_skipped += 1
            logger.info("sync_skipped", code=code, reason="already covered")
            if progress:
                progress(index, len(codes), code, 0)
            continue

        written = 0
        try:
            bars = provider.get_bars(code, start, end, freq)
            written = store.upsert_bars(bars)
            result.bars_written += written

            factor_rows = 0
            if with_factors and provider.supports(Capability.FACTORS):
                factors = provider.get_factors(code, start, end)
                factor_rows = store.upsert_factors(factors)
                result.factors_written += factor_rows

            store.record_sync(code, freq, start, end, written)
            result.codes_synced += 1
            logger.info("sync_code_done", code=code, bars=written, factors=factor_rows)
        except DataSourceError as exc:
            # Keep going: a single delisted or misspelled symbol should not
            # throw away the codes already fetched.
            result.codes_failed += 1
            result.failures[code] = exc.message
            logger.warning("sync_code_failed", code=code, error=exc.message)

        if progress:
            progress(index, len(codes), code, written)

    result.elapsed_seconds = monotonic() - started
    logger.info("sync_done", **{k: v for k, v in vars(result).items() if k != "failures"})
    return result


def _already_covered(
    store: MarketStore, code: str, freq: Freq, start: date, end: date
) -> bool:
    """Whether ``code`` already has data covering the whole requested window."""
    span = store.synced_span(code, freq)
    return span is not None and span[0] <= start and span[1] >= end


def resolve_codes(
    provider: DataProvider, *, index: str | None = None, codes: Iterable[str] | None = None
) -> list[str]:
    """Work out which codes to sync.

    Args:
        provider: Source, used to resolve an index's constituents.
        index: Index name such as ``csi300``.
        codes: Explicit codes, which take precedence over ``index``.

    Returns:
        Canonical codes, de-duplicated but order-preserving.

    Raises:
        DataSourceError: neither an index nor explicit codes were given.
    """
    if codes is not None:
        selected = list(codes)
    elif index is not None:
        resolver = getattr(provider, "get_index_constituents", None)
        if resolver is None:
            raise DataSourceError(
                f"provider {provider.name!r} cannot resolve index constituents",
                {"provider": provider.name},
            )
        selected = resolver(index)
    else:
        raise DataSourceError("either index or codes must be given")

    seen: dict[str, None] = {}
    for code in selected:
        seen.setdefault(code, None)
    return list(seen)


def sync_universe(
    store: MarketStore,
    provider: DataProvider,
    start: date,
    end: date,
    *,
    index: str | None = None,
    codes: Iterable[str] | None = None,
    freq: Freq = Freq.DAY,
    resume: bool = True,
    with_factors: bool = True,
    progress: ProgressFn | None = None,
) -> SyncResult:
    """Convenience wrapper: resolve a universe, then sync the calendar and it."""
    selected = resolve_codes(provider, index=index, codes=codes)
    result = sync_codes(
        store,
        provider,
        selected,
        start,
        end,
        freq=freq,
        resume=resume,
        with_factors=with_factors,
        progress=progress,
    )
    result.calendar_days = sync_calendar(store, provider, start, end, freq)
    return result
