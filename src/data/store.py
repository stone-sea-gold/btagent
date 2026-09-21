"""DuckDB market-data warehouse.

The store is the system's source of truth for market data: providers write into
it, and everything downstream — factor computation, the Qlib exporter, the
backtest engine — reads from it rather than from a data source directly.

Two properties make that split worthwhile:

* **Sync is decoupled from use.** A backtest never waits on a data source, and
  a source outage cannot change a past result.
* **Cross-source reconciliation becomes possible.** Because raw prices are
  stored once with a ``source`` column, two providers' rows sit side by side and
  can be compared day by day.

Layout
------
``bars`` holds unadjusted prices only and is keyed on ``(freq, code, ts)``, so
daily and intraday bars coexist in one table and a re-sync is idempotent.

``adjust_factors`` holds the back-adjustment factor separately. Keeping it out
of ``bars`` is what makes the raw series stable: a new dividend extends the
factor table without rewriting a single historical price.

``sync_state`` records the span already fetched per ``(code, freq)``. That is
what makes ``--resume`` possible — an interrupted run picks up where it stopped
instead of re-fetching everything.

Every write is an ``INSERT OR REPLACE`` on the primary key, so running the same
sync twice leaves the table in exactly the state one run would.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Self

import pandas as pd

from src.config import settings
from src.data.schema import AdjustFactor, Bar, Freq, Instrument
from src.exceptions import DataSourceError
from src.logging import get_logger

logger = get_logger(__name__)

_BAR_COLUMNS = (
    "freq",
    "code",
    "ts",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "amount",
    "is_suspended",
    "pct_change",
    "source",
)

def _utc_now() -> datetime:
    """Current UTC time as a naive timestamp — see the sync_state column note."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


#: Columns added after the initial schema, as (table, column, DDL fragment).
_ADDED_COLUMNS: tuple[tuple[str, str, str], ...] = (
    ("bars", "pct_change", "pct_change DOUBLE"),
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS bars (
    freq         VARCHAR NOT NULL,
    code         VARCHAR NOT NULL,
    ts           TIMESTAMP NOT NULL,
    open         DOUBLE NOT NULL,
    high         DOUBLE NOT NULL,
    low          DOUBLE NOT NULL,
    close        DOUBLE NOT NULL,
    volume       DOUBLE NOT NULL,
    amount       DOUBLE NOT NULL,
    is_suspended BOOLEAN NOT NULL DEFAULT FALSE,
    source       VARCHAR NOT NULL DEFAULT '',
    PRIMARY KEY (freq, code, ts)
);

CREATE TABLE IF NOT EXISTS adjust_factors (
    code   VARCHAR NOT NULL,
    ts     DATE NOT NULL,
    factor DOUBLE NOT NULL,
    source VARCHAR NOT NULL DEFAULT '',
    PRIMARY KEY (code, ts)
);

CREATE TABLE IF NOT EXISTS calendar (
    freq VARCHAR NOT NULL,
    ts   DATE NOT NULL,
    PRIMARY KEY (freq, ts)
);

CREATE TABLE IF NOT EXISTS instruments (
    code       VARCHAR PRIMARY KEY,
    name       VARCHAR NOT NULL DEFAULT '',
    start_date DATE NOT NULL,
    end_date   DATE NOT NULL
);

-- What has already been fetched, per code and frequency. Drives --resume.
CREATE TABLE IF NOT EXISTS sync_state (
    code        VARCHAR NOT NULL,
    freq        VARCHAR NOT NULL,
    start_date  DATE NOT NULL,
    end_date    DATE NOT NULL,
    rows_written BIGINT NOT NULL DEFAULT 0,
    -- An audit instant, recorded in UTC. Unlike bars.ts, which is an exchange
    -- calendar date and therefore naive by design. Stored without a timezone
    -- tag because reading a TIMESTAMPTZ back into Python makes DuckDB require
    -- pytz, which is a poor trade for a field nothing queries.
    updated_at  TIMESTAMP NOT NULL,
    PRIMARY KEY (code, freq)
);
"""


class MarketStore:
    """A local DuckDB warehouse of unadjusted bars and adjustment factors."""

    def __init__(self, db_path: str | None = None) -> None:
        self._db_path = db_path or settings.market_data_db
        self._connection: Any = None

    # ── lifecycle ──────────────────────────────────────────────────

    @property
    def db_path(self) -> str:
        """Path of the DuckDB file backing this store."""
        return self._db_path

    def connect(self) -> Any:
        """Open the database, creating the file and schema on first use."""
        if self._connection is not None:
            return self._connection
        import duckdb

        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._connection = duckdb.connect(self._db_path)
        self._connection.execute(_SCHEMA)
        self._migrate()
        logger.info("market_store_opened", db_path=self._db_path)
        return self._connection

    def _migrate(self) -> None:
        """Add columns introduced after a database was first created.

        ``CREATE TABLE IF NOT EXISTS`` leaves an existing table untouched, so a
        warehouse built by an earlier version would be missing newer columns
        while ``sync_state`` still claimed full coverage — the sync would skip
        every code and the gap would go unnoticed. Adding the columns in place
        avoids that trap without requiring a re-sync.
        """
        for table, column, ddl in _ADDED_COLUMNS:
            existing = {
                row[0]
                for row in self._connection.execute(
                    f"SELECT column_name FROM information_schema.columns "
                    f"WHERE table_name = '{table}'"
                ).fetchall()
            }
            if column not in existing:
                self._connection.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")
                logger.info("market_store_migrated", table=table, column=column)

    def close(self) -> None:
        """Close the database, flushing any pending writes."""
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    def __enter__(self) -> Self:
        self.connect()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    # ── writes ─────────────────────────────────────────────────────

    def _replace_from_frame(self, table: str, columns: Sequence[str], rows: Sequence[tuple]) -> int:
        """Bulk-upsert rows, replacing any existing primary key."""
        if not rows:
            return 0
        connection = self.connect()
        frame = pd.DataFrame(list(rows), columns=list(columns))
        connection.register("_incoming", frame)
        try:
            column_list = ", ".join(columns)
            connection.execute(
                f"INSERT OR REPLACE INTO {table} ({column_list}) "
                f"SELECT {column_list} FROM _incoming"
            )
        finally:
            connection.unregister("_incoming")
        return len(rows)

    def upsert_bars(self, bars: Iterable[Bar]) -> int:
        """Write bars, replacing rows that already exist."""
        rows = [
            (
                bar.freq.value,
                bar.code,
                bar.ts,
                bar.open,
                bar.high,
                bar.low,
                bar.close,
                bar.volume,
                bar.amount,
                bar.is_suspended,
                bar.pct_change,
                bar.source,
            )
            for bar in bars
        ]
        written = self._replace_from_frame("bars", _BAR_COLUMNS, rows)
        logger.info("market_store_bars_written", rows=written)
        return written

    def upsert_factors(self, factors: Iterable[AdjustFactor]) -> int:
        """Write adjustment factors, replacing rows that already exist."""
        rows = [
            (factor.code, factor.ts, factor.factor, factor.source) for factor in factors
        ]
        return self._replace_from_frame(
            "adjust_factors", ("code", "ts", "factor", "source"), rows
        )

    def upsert_calendar(self, freq: Freq, days: Iterable[date]) -> int:
        """Write trading days for one frequency."""
        rows = [(freq.value, day) for day in days]
        return self._replace_from_frame("calendar", ("freq", "ts"), rows)

    def upsert_instruments(self, instruments: Iterable[Instrument]) -> int:
        """Write securities and their listing spans."""
        rows = [
            (item.code, item.name, item.start_date, item.end_date)
            for item in instruments
        ]
        return self._replace_from_frame(
            "instruments", ("code", "name", "start_date", "end_date"), rows
        )

    # ── reads ──────────────────────────────────────────────────────

    def get_bars(
        self,
        code: str,
        start: date,
        end: date,
        freq: Freq = Freq.DAY,
    ) -> list[Bar]:
        """Read bars for one security, ascending by timestamp."""
        connection = self.connect()
        cursor = connection.execute(
            f"SELECT {', '.join(_BAR_COLUMNS)} FROM bars "
            "WHERE code = ? AND freq = ? AND ts >= ? AND ts <= ? ORDER BY ts",
            [code, freq.value, datetime.combine(start, datetime.min.time()),
             datetime.combine(end, datetime.max.time())],
        )
        return [
            Bar(
                freq=Freq(row[0]),
                code=row[1],
                ts=row[2],
                open=row[3],
                high=row[4],
                low=row[5],
                close=row[6],
                volume=row[7],
                amount=row[8],
                is_suspended=row[9],
                pct_change=row[10],
                source=row[11],
            )
            for row in cursor.fetchall()
        ]

    def get_factors(self, code: str, start: date, end: date) -> list[AdjustFactor]:
        """Read adjustment factors for one security, ascending by date."""
        connection = self.connect()
        cursor = connection.execute(
            "SELECT code, ts, factor, source FROM adjust_factors "
            "WHERE code = ? AND ts >= ? AND ts <= ? ORDER BY ts",
            [code, start, end],
        )
        return [
            AdjustFactor(code=row[0], ts=row[1], factor=row[2], source=row[3])
            for row in cursor.fetchall()
        ]

    def get_calendar(self, start: date, end: date, freq: Freq = Freq.DAY) -> list[date]:
        """Read trading days, ascending."""
        connection = self.connect()
        cursor = connection.execute(
            "SELECT ts FROM calendar WHERE freq = ? AND ts >= ? AND ts <= ? ORDER BY ts",
            [freq.value, start, end],
        )
        return [row[0] for row in cursor.fetchall()]

    def codes(self, freq: Freq = Freq.DAY) -> list[str]:
        """Every code that has bars at this frequency."""
        connection = self.connect()
        cursor = connection.execute(
            "SELECT DISTINCT code FROM bars WHERE freq = ? ORDER BY code", [freq.value]
        )
        return [row[0] for row in cursor.fetchall()]

    def factor_codes(self) -> list[str]:
        """Every code that has adjustment factors.

        Kept separate from :meth:`codes`, which reads ``bars``: the factor chain
        is meaningful on its own, and a code could in principle carry factors
        without any bars in the stored window.
        """
        connection = self.connect()
        cursor = connection.execute(
            "SELECT DISTINCT code FROM adjust_factors ORDER BY code"
        )
        return [row[0] for row in cursor.fetchall()]

    def coverage(self, freq: Freq = Freq.DAY) -> dict[str, Any]:
        """Summarize what the warehouse holds, for reporting and diagnostics."""
        connection = self.connect()
        row = connection.execute(
            "SELECT COUNT(*), COUNT(DISTINCT code), MIN(ts), MAX(ts) "
            "FROM bars WHERE freq = ?",
            [freq.value],
        ).fetchone()
        bars, code_count, first, last = row
        return {
            "freq": freq.value,
            "bars": bars,
            "codes": code_count,
            "first_date": first.date() if first else None,
            "last_date": last.date() if last else None,
            "factor_rows": connection.execute(
                "SELECT COUNT(*) FROM adjust_factors"
            ).fetchone()[0],
            "calendar_days": connection.execute(
                "SELECT COUNT(*) FROM calendar WHERE freq = ?", [freq.value]
            ).fetchone()[0],
        }

    # ── sync bookkeeping ───────────────────────────────────────────

    def synced_span(self, code: str, freq: Freq = Freq.DAY) -> tuple[date, date] | None:
        """The span already fetched for ``code``, or ``None`` if never synced."""
        connection = self.connect()
        row = connection.execute(
            "SELECT start_date, end_date FROM sync_state WHERE code = ? AND freq = ?",
            [code, freq.value],
        ).fetchone()
        return (row[0], row[1]) if row else None

    def record_sync(
        self,
        code: str,
        freq: Freq,
        start: date,
        end: date,
        rows_written: int,
    ) -> None:
        """Record that ``[start, end]`` has been fetched for ``code``.

        The recorded span is widened, never narrowed, so syncing an adjacent
        window extends coverage instead of resetting it.
        """
        existing = self.synced_span(code, freq)
        if existing is not None:
            start = min(start, existing[0])
            end = max(end, existing[1])
        self.connect().execute(
            "INSERT OR REPLACE INTO sync_state "
            "(code, freq, start_date, end_date, rows_written, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [code, freq.value, start, end, rows_written, _utc_now()],
        )

    def synced_codes(self, freq: Freq = Freq.DAY) -> set[str]:
        """Codes with a recorded sync at this frequency."""
        connection = self.connect()
        cursor = connection.execute(
            "SELECT code FROM sync_state WHERE freq = ?", [freq.value]
        )
        return {row[0] for row in cursor.fetchall()}


def open_store(db_path: str | None = None) -> MarketStore:
    """Open a store, failing with a clear message when DuckDB is unavailable."""
    try:
        import duckdb  # noqa: F401
    except ImportError as exc:  # pragma: no cover - dependency is declared
        raise DataSourceError(
            "duckdb is not installed; run `pip install duckdb`"
        ) from exc
    return MarketStore(db_path)
