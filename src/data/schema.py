"""Canonical market-data models shared by every data source.

These models are the contract between the provider adapters, the DuckDB
warehouse, and everything downstream (factor computation, the Qlib exporter,
the backtest engine). Every provider converts its native payload into these
shapes at its own boundary, so the rest of the system never sees a
source-specific field name.

Unit conventions — these are normative, not decorative
-----------------------------------------------------
A-share sources disagree about units, and the disagreements are silent. The
same stock pulled from two sources can differ by a factor of 100:

    field     unit used here   what sources actually send
    --------  ---------------  --------------------------------------------
    price     CNY per share    consistent across sources
    volume    shares           BaoStock sends shares, Sina and Tencent send
                               手 (lots of 100) — a 100x discrepancy
    amount    CNY              some sources send 千元 or 万元

Normalizing here is what makes cross-source reconciliation meaningful: two
providers agreeing on a raw (unadjusted) close can be compared day by day, and
a 100x volume mismatch shows up as a real error instead of a silent one.

Price adjustment
----------------
``Bar`` prices are **unadjusted (raw) traded prices**, always. Adjusted prices
are never stored, because:

* raw prices are an objective fact that every source agrees on, which is what
  makes cross-source verification possible;
* forward-adjusted (前复权) prices are recomputed from the latest price
  backwards, so every new dividend rewrites the entire history — a backtest
  built on them is not reproducible;
* the adjustment factor is stored separately in :class:`AdjustFactor`, so
  adjusted series are derived on read.

This mirrors Qlib's own architecture: Qlib keeps a ``factor.day.bin`` alongside
the price fields and falls back to "adjusted price mode" (with ``trade_unit``
disabled) when that field is missing.
"""

from __future__ import annotations

import math
from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, Field, field_validator

from src.data.codes import normalize
from src.exceptions import DataSourceError


def _require_canonical(value: str) -> str:
    """Canonicalize a security code inside a Pydantic validator.

    Pydantic only converts :class:`ValueError` into a ``ValidationError``, so a
    :class:`DataSourceError` raised by the parser would escape the model's
    validation contract and force callers to catch two unrelated exception
    types. Re-raising as ``ValueError`` keeps every bad field value surfacing
    as a ``ValidationError``.
    """
    try:
        return normalize(value)
    except DataSourceError as exc:
        raise ValueError(exc.message) from exc


class Freq(str, Enum):
    """Bar frequency.

    The values are exactly Qlib's frequency strings, so they can be used
    directly in Qlib file names (``close.day.bin``, ``calendars/1min.txt``)
    without a translation table.
    """

    DAY = "day"
    MIN_1 = "1min"
    MIN_5 = "5min"
    MIN_15 = "15min"
    MIN_30 = "30min"
    MIN_60 = "60min"

    @property
    def is_intraday(self) -> bool:
        """Whether this frequency is finer than a trading day."""
        return self is not Freq.DAY


class Bar(BaseModel):
    """One OHLCV bar for one security.

    Attributes:
        freq: Bar frequency.
        code: Canonical security code, e.g. ``600519.SH``.
        ts: Bar timestamp. For daily bars this is midnight of the trading day,
            so daily and intraday bars can share one table.
        open: Open price, CNY per share, unadjusted.
        high: High price, CNY per share, unadjusted.
        low: Low price, CNY per share, unadjusted.
        close: Close price, CNY per share, unadjusted.
        volume: Traded volume in **shares**, never in 手.
        amount: Traded value in **CNY**.
        is_suspended: Whether the security was suspended on this bar.

            Sources differ here: some emit a flat bar (open = high = low =
            close = previous close, volume 0) for a suspended day and some omit
            the date entirely. Providers must normalize to this flag so that a
            suspension is never mistaken for a tradable day.
        pct_change: The exchange's published daily change, as a fraction.

            Optional, and present only when a source supplies it. It is kept
            because it is authoritative: the exchange computes the previous
            close net of corporate actions, which is exactly the value
            :mod:`src.data.derive` has to reproduce from the adjustment factor.
            Holding it makes that check possible offline and repeatably, rather
            than requiring a re-fetch every time.
        source: Provider name this row came from, for provenance and
            cross-source reconciliation.
    """

    freq: Freq = Freq.DAY
    code: str
    ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = Field(ge=0.0)
    amount: float = Field(ge=0.0)
    is_suspended: bool = False
    pct_change: float | None = None
    source: str = ""

    @field_validator("code")
    @classmethod
    def _canonical_code(cls, value: str) -> str:
        """Reject non-canonical codes so the warehouse stays uniformly keyed."""
        return _require_canonical(value)

    @field_validator("volume", "amount")
    @classmethod
    def _finite(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("volume/amount must be finite")
        return value

    @property
    def trading_date(self) -> date:
        """Trading day this bar belongs to, ignoring the time component."""
        return self.ts.date()


class AdjustFactor(BaseModel):
    """Cumulative back-adjustment factor for one security on one day.

    The factor relates the raw and adjusted series by::

        hfq_price = raw_price * factor

    Qlib's ``factor.day.bin`` holds this same quantity, which is what lets a
    backtest round order sizes to whole lots (``trade_unit`` = 100 shares for
    A-shares) while the reported prices stay on the raw series.

    Sources rarely expose this as a table — BaoStock, for instance, only
    returns already-adjusted prices. It is recovered by dividing a
    back-adjusted close by the raw close on the same day, which is exact
    because both series are published per trading day.

    Factors are stored at daily granularity only. Intraday bars reuse the
    factor of their trading day, which is the standard treatment and avoids
    per-minute factor disagreement between sources.
    """

    code: str
    ts: date
    factor: float = Field(gt=0.0)
    source: str = ""

    @field_validator("code")
    @classmethod
    def _canonical_code(cls, value: str) -> str:
        return _require_canonical(value)


class Instrument(BaseModel):
    """A listed security and the span over which it traded.

    The date range matters for backtests: a stock that listed in 2021 must not
    appear in a 2018 cross-section, and a delisted stock must stop appearing
    from its delisting day. This mirrors Qlib's ``instruments/all.txt``, whose
    rows are ``SYMBOL  start  end``.
    """

    code: str
    name: str = ""
    start_date: date
    end_date: date

    @field_validator("code")
    @classmethod
    def _canonical_code(cls, value: str) -> str:
        return _require_canonical(value)

    @field_validator("end_date")
    @classmethod
    def _ordered(cls, value: date, info) -> date:
        start = info.data.get("start_date")
        if start is not None and value < start:
            raise ValueError(f"end_date {value} precedes start_date {start}")
        return value
