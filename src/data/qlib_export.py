"""Export the DuckDB warehouse as a Qlib dataset.

Qlib reads its own binary layout — a shared trading calendar, an instrument
file, and one ``<field>.<freq>.bin`` per field per security, each containing a
float32 array whose first element is the security's index into that calendar::

    qlib_dir/
    ├── calendars/day.txt            # one "%Y-%m-%d" per trading day
    ├── instruments/all.txt          # SH600519\t2020-01-02\t2024-12-31
    └── features/sh600519/
        ├── open.day.bin
        ├── close.day.bin
        ├── volume.day.bin
        ├── factor.day.bin
        └── change.day.bin

Two conventions are decided here and matter far beyond file layout:

**Adjusted prices.** ``close`` (and the other price fields) are written
back-adjusted, and ``factor`` holds the cumulative back-adjustment ratio. When
Qlib's ``Exchange`` sees a non-NaN ``$factor`` it rounds order sizes to whole
lots — ``(deal_amount × factor) // 100 × 100 / factor`` lands on multiples of
100 shares only if ``deal_amount × factor`` is a share count on the raw series,
which is consistent with ``$close`` being the adjusted price and ``$factor`` the
adjusted-to-raw ratio. Without ``$factor``, Qlib falls back to adjusted-price
mode and disables that rounding with a warning.

**Suspensions become NaN, not flat bars.** BaoStock reports a halted day as a
flat bar whose OHLC all equal the previous close; written through unchanged, a
backtest would take that as a tradable price and fill orders on a day the stock
could not be traded. Qlib instead infers a suspension from a *missing* close
(``Exchange.check_stock_suspended``), so halted days are written as NaN across
the traded fields while ``factor`` keeps its value — it is defined on those days
too, and a NaN there would trigger Qlib's adjusted-price fallback and disable
lot rounding for the whole run.

``change`` is the adjusted daily return; :mod:`src.data.derive` explains why the
raw-price route is wrong on ex-dividend dates.

Index data (used as backtest benchmarks) is handled specially: their features
are exported so Qlib can value the benchmark series, but they are *not* written
into ``instruments/all.txt`` — a trading universe that offered the index itself
as a candidate would let a top-k selection "trade" the index, which is not a
traded instrument.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import date
from pathlib import Path

import numpy as np

from src.data.codes import normalize, to_qlib
from src.data.derive import derive_series
from src.data.schema import Freq
from src.data.store import MarketStore
from src.exceptions import DataSourceError
from src.logging import get_logger

logger = get_logger(__name__)

#: Fields written out. ``factor`` and ``change`` are first-class Qlib fields:
#: the former drives lot rounding, the latter drives limit-move detection.
FIELDS = ("open", "high", "low", "close", "volume", "factor", "change")

_DATE_FORMAT = "%Y-%m-%d"
# Bins are little-endian float32, matching Qlib's dumps.
_BIN_DTYPE = "<f4"


class QlibExporter:
    """Export the warehouse as a Qlib day-frequency dataset."""

    def __init__(
        self,
        out_dir: str | Path,
        freq: Freq = Freq.DAY,
        exclude_from_universe: Iterable[str] = (),
    ) -> None:
        self._out_dir = Path(out_dir)
        self._freq = freq
        # Codes with features but no instruments/all.txt line: benchmarks the
        # backtest values but must not enter the tradable universe.
        self._universe_excluded = {normalize(c) for c in exclude_from_universe}

    @property
    def _suffix(self) -> str:
        return f"{self._freq.value}.bin"

    def export(
        self,
        store: MarketStore,
        codes: Iterable[str] | None = None,
        start: date | None = None,
        end: date | None = None,
    ) -> dict[str, int]:
        """Write ``codes`` over ``[start, end]`` in Qlib's layout.

        Args:
            store: Warehouse to read from.
            codes: Codes to export; defaults to every code with bars.
            start: First trading day to include.
            end: Last trading day to include.

        Returns:
            Counts of exported instruments, calendar days and fields.
        """
        """Write ``codes`` over ``[start, end]`` in Qlib's layout.

        Args:
            store: Warehouse to read from.
            codes: Codes to export; defaults to every code with bars.
            start: First trading day to include.
            end: Last trading day to include.

        Returns:
            Counts of exported instruments, calendar days and fields.

        Raises:
            DataSourceError: a calendar day falls outside the synced calendar
                while bars exist for a code on it.
        """
        selected = list(codes) if codes is not None else store.codes()
        if not selected:
            raise DataSourceError("nothing to export: the warehouse holds no codes")

        series = self._derived_rows(store, selected, start, end)

        calendar = sorted({row.trading_date for rows in series.values() for row in rows})
        day_index = {day: i for i, day in enumerate(calendar)}

        self._write_file(
            "calendars", f"{self._freq.value}.txt",
            "\n".join(day.strftime(_DATE_FORMAT) for day in calendar) + "\n",
        )

        features_dir = self._out_dir / "features"
        lines: list[str] = []
        for code, rows in sorted(series.items()):
            self._write_features(features_dir, code, day_index, rows)
            if code not in self._universe_excluded:
                lines.append(
                    f"{to_qlib(code)}\t{rows[0].trading_date}\t{rows[-1].trading_date}"
                )
        self._write_file("instruments", "all.txt", "\n".join(lines) + "\n")

        counts = {
            "instruments": len(lines),
            "features": len(series),
            "days": len(calendar),
            "fields": len(FIELDS),
        }
        logger.info("qlib_export_done", out_dir=str(self._out_dir), **counts)
        return counts

    # ── internals ──────────────────────────────────────────────────

    def _derived_rows(
        self,
        store: MarketStore,
        selected: Sequence[str],
        start: date | None,
        end: date | None,
    ) -> dict[str, list]:
        start = start or date(1990, 1, 1)
        end = end or date(2100, 1, 1)
        out: dict[str, list] = {}
        for code in selected:
            bars = store.get_bars(code, start, end, self._freq)
            factors = store.get_factors(code, start, end)
            if not bars or not factors:
                logger.warning("qlib_export_skipped", code=code, reason="no bars or factors")
                continue
            out[code] = derive_series(bars, factors)
        if not out:
            raise DataSourceError(
                "no securable rows: every requested code lacked bars or factors",
                {"codes": len(selected)},
            )
        return out

    def _write_features(
        self, features_dir: Path, code: str, day_index: dict[date, int], rows: Sequence
    ) -> None:
        security_dir = features_dir / to_qlib(code).lower()
        security_dir.mkdir(parents=True, exist_ok=True)

        values = np.full((len(day_index), len(FIELDS)), np.nan, dtype=np.float64)
        for row in rows:
            index = day_index.get(row.trading_date)
            if index is None:
                raise DataSourceError(
                    f"{code} trades on {row.trading_date}, which is not in the "
                    "shared calendar; re-read the calendar or widen the export",
                    {"code": code, "date": row.trading_date.isoformat()},
                )
            for column, field in enumerate(FIELDS):
                if row.is_suspended and field != "factor":
                    continue  # halted day: keep NaN so Qlib reads it as suspended
                values[index, column] = getattr(row, field)

        for column, field in enumerate(FIELDS):
            # Qlib bins are float32 with the calendar offset prepended.
            payload = np.hstack([[day_index[rows[0].trading_date]], values[:, column]])
            (security_dir / f"{field}.{self._freq.value}.bin").write_bytes(
                payload.astype(_BIN_DTYPE).tobytes()
            )

    def _write_file(self, subdir: str, name: str, content: str) -> None:
        directory = self._out_dir / subdir
        directory.mkdir(parents=True, exist_ok=True)
        (directory / name).write_text(content, encoding="utf-8")


def write_qlib_dataset(
    store: MarketStore,
    out_dir: str | Path,
    codes: Iterable[str] | None = None,
    start: date | None = None,
    end: date | None = None,
    exclude_from_universe: Iterable[str] = (),
) -> dict[str, int]:
    """Export ``store`` into ``out_dir`` in Qlib's layout. See :class:`QlibExporter`."""
    return QlibExporter(out_dir, exclude_from_universe=exclude_from_universe).export(
        store, codes, start, end
    )
