"""BaoStock data provider — the primary daily source.

BaoStock is the preferred source because it is an official SDK rather than a
scraper, and because it is the only candidate that serves all four capability
domains with a stable interface.

Which endpoints this provider uses, and what was verified about each
--------------------------------------------------------------------
BaoStock exposes 26 ``query_*`` functions. Four matter here:

    capability     endpoint                          verified behaviour
    -------------  --------------------------------  ------------------------
    bars           query_history_k_data_plus         adjustflag 1/2/3 selects
                                                     back/forward/no adjustment
    factors        query_adjust_factor               sparse: one row per
                                                     ex-dividend event only
    calendar       query_trade_dates                 is_trading_day is "1"/"0"
    instruments    query_hs300_stocks,               index constituents carry
                   query_stock_basic                 listing/delisting dates

Everything below was measured against the live service rather than inferred
from documentation:

* **Volume is in shares, not lots.** For 600519 on 2020-01-02 the response was
  ``volume=14809916, amount=16696837095``; ``amount / volume = 1127`` CNY, which
  matches that day's close of 1130. Had volume been in 手 the ratio would have
  been 100x the price. Sina and Tencent, by contrast, send 手 — see
  :mod:`src.data.schema` for why this is normalized at the boundary.
* **Every field arrives as a string**, including numerics, and prices carry four
  decimal places. Conversion is explicit below.
* **A suspended day comes back as a flagged flat bar, not as a missing row.**
  600009 on 2022-04-08 — a trading day it was halted — returned::

      date        open    high    low     close   preclose  volume  amount  tradestatus
      2022-04-08  50.4300 50.4300 50.4300 50.4300 50.4300   ""      ""      "0"

  OHLC collapse onto the previous close, ``volume`` and ``amount`` arrive as
  empty strings rather than zeros, and ``tradestatus`` reads ``"0"``. Bars are
  emitted with ``is_suspended=True`` and zeroed volume rather than dropped, so
  the halt stays visible downstream.

  This matters for the Qlib export: Qlib infers a suspension from a *missing*
  ``$close`` (``Exchange.check_stock_suspended``), so writing this flat bar
  through unchanged would advertise a tradable price on a day the stock could
  not be traded. The exporter must render suspended days as NaN.

  An earlier probe of 600519 and 000001 showed no such rows and led to the
  wrong conclusion that halts are omitted entirely; those two simply never
  halted within the sampled window. Breadth of test data, not only depth, is
  what surfaces this class of quirk.
* **``query_stock_basic`` is capped at 4000 rows** when called without a code,
  which is fewer than the A-share universe and silently excludes most Shanghai
  main-board names (600519 is not in the result). Per-code queries are exact.
  The full-universe path uses index constituents instead.
* **One stock's five years of daily bars takes ~4 seconds**, so fetching the
  CSI 300 over five years is on the order of 20 minutes.

Adjustment factors deserve their own note
-----------------------------------------
``query_adjust_factor`` returns one row per ex-dividend event, so five years of
Moutai is nine rows. Two consequences shape :meth:`BaoStockProvider.get_factors`:

1. The series must be forward-filled to every trading day. Qlib's ``Exchange``
   degrades whenever *any* ``$factor`` value is NaN — it disables ``trade_unit``
   (whole-lot rounding, 100 shares for A-shares) and logs a warning — so a
   sparse factor table is not usable as-is.
2. The query starts from the beginning of history rather than from ``start``.
   Taking the first in-window event and back-filling it would apply a dividend
   adjustment to days *before* that dividend, which is a look-ahead bias. Since
   the response is sparse, scanning from 1990 costs almost nothing.

The ``adjustFactor`` column is deliberately ignored in favour of
``backAdjustFactor``: on some rows (600519 on 2023-06-30) the two disagree,
``adjustFactor`` reading 0.988591 against ``backAdjustFactor`` 6.889798. Only
the latter behaves as a cumulative back-adjustment factor. Pinning down the
exact scaling convention Qlib expects is a separate calibration step.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime
from typing import Any, Self

from src.data.codes import parse
from src.data.derive import enforce_monotonic_chain
from src.data.provider import Capability, DataProvider
from src.data.schema import AdjustFactor, Bar, Freq, Instrument
from src.exceptions import DataSourceError
from src.logging import get_logger

logger = get_logger(__name__)

#: Fields requested for daily bars. ``preclose`` and ``pctChg`` are fetched so
#: that a cross-source check can validate the change series without recomputing
#: it, and ``tradestatus``/``isST`` are kept for diagnostics.
DAILY_FIELDS = "date,open,high,low,close,preclose,volume,amount,tradestatus,pctChg,isST"

#: BaoStock frequency codes. Only ``d`` is wired up for now; the intraday codes
#: are listed so the mapping is visible when minute bars are added.
FREQ_CODES: dict[Freq, str] = {
    Freq.DAY: "d",
    Freq.MIN_5: "5",
    Freq.MIN_15: "15",
    Freq.MIN_30: "30",
    Freq.MIN_60: "60",
}

#: BaoStock's back-adjustment flag: 1 = back-adjusted, 2 = forward-adjusted,
#: 3 = raw. Raw is what the warehouse stores.
ADJUST_RAW = "3"

#: ``tradestatus`` value reported on a halted trading day.
SUSPENDED = "0"

#: BaoStock's security types, from the ``type`` column of ``query_stock_basic``.
TYPE_STOCK = "1"
TYPE_INDEX = "2"
TYPE_CONVERTIBLE_BOND = "4"
TYPE_FUND = "5"

#: Earliest date worth asking about; BaoStock's own data starts well after this.
_EPOCH = date(1990, 1, 1)

#: Base of the back-adjustment chain, used for days preceding the first recorded
#: corporate action (a security that has never paid a dividend).
_FACTOR_BASE = 1.0


def _to_float(value: str) -> float | None:
    """Convert a BaoStock numeric string, treating blanks as absent."""
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError as exc:
        raise DataSourceError(f"cannot parse numeric field {value!r}") from exc


def _require_float(value: str, field: str, context: str) -> float:
    """Convert a required numeric field, failing loudly when absent."""
    number = _to_float(value)
    if number is None:
        raise DataSourceError(f"missing required field {field!r} for {context}")
    return number


def _to_date(value: str) -> date:
    """Parse BaoStock's ``YYYY-MM-DD`` dates."""
    return date.fromisoformat(value.strip())


def _volume_like(
    value: str, *, suspended: bool, field: str, context: str
) -> float:
    """Read volume or amount, tolerating the blanks BaoStock sends on halted days.

    A suspended day comes back as a flat bar (OHLC all equal to the previous
    close) with ``volume`` and ``amount`` empty rather than zero, so an empty
    value here means "no trading happened", not "the field is missing".
    """
    number = _to_float(value)
    if number is not None:
        return number
    if suspended:
        return 0.0
    raise DataSourceError(f"missing required field {field!r} for {context}")


def _percent_to_fraction(value: str) -> float | None:
    """Convert BaoStock's percentage string ("-4.480100") to a fraction.

    The exchange's published change is stored alongside the derived one so the
    two can be compared offline. Blank on a halted day, hence optional.
    """
    percent = _to_float(value)
    return None if percent is None else percent / 100.0


def _factor_on(actions: list[tuple[date, float]], day: date) -> float:
    """Back-adjustment factor in force on ``day``.

    The factor is piecewise constant: a corporate action sets a new value that
    holds until the next one, and days preceding the first recorded action take
    :data:`_FACTOR_BASE`.

    Only actions at or before ``day`` are considered. Reaching for a later action
    would apply a dividend to days before it happened — a look-ahead bias, and
    the classic way to make a backtest look better than it is.
    """
    factor = _FACTOR_BASE
    for action_date, action_factor in actions:
        if action_date > day:
            break
        factor = action_factor
    return factor


class BaoStockProvider(DataProvider):
    """Daily market data from BaoStock.

    The underlying library keeps module-global session state, so a provider
    instance owns one login. Use it as a context manager, or call
    :meth:`close` when finished.
    """

    name = "baostock"

    def __init__(self, *, max_attempts: int = 3) -> None:
        self._max_attempts = max_attempts
        self._logged_in = False

    # ── session ────────────────────────────────────────────────────

    def _bs(self) -> Any:
        """Import BaoStock lazily so the package stays importable without it."""
        try:
            import baostock
        except ImportError as exc:  # pragma: no cover - dependency is declared
            raise DataSourceError(
                "baostock is not installed; run `pip install baostock`"
            ) from exc
        return baostock

    def _login(self) -> Any:
        bs = self._bs()
        if self._logged_in:
            return bs
        result = bs.login()
        if result.error_code != "0":
            raise DataSourceError(
                f"baostock login failed: {result.error_msg}",
                {"error_code": result.error_code},
            )
        self._logged_in = True
        return bs

    def close(self) -> None:
        """Log out, releasing the session."""
        if not self._logged_in:
            return
        try:
            self._bs().logout()
        finally:
            self._logged_in = False

    def __enter__(self) -> Self:
        self._login()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    # ── declaration ────────────────────────────────────────────────

    def capabilities(self) -> frozenset[Capability]:
        # INSTRUMENTS is deliberately absent: listing spans are only available
        # one code at a time, so a whole-market universe cannot be served
        # cheaply. See get_instruments.
        return frozenset({Capability.BARS, Capability.FACTORS, Capability.CALENDAR})

    def freqs(self) -> frozenset[Freq]:
        # BaoStock serves 5/15/30/60-minute bars too, but only daily is wired up;
        # declaring them here would promise data this provider cannot yet return.
        return frozenset({Freq.DAY})

    # ── internals ──────────────────────────────────────────────────

    def _drain(self, result: Any, what: str, code: str) -> list[dict[str, str]]:
        """Collect a query result as name-keyed rows.

        BaoStock returns columns in the order they were requested, so reading by
        position would silently mis-assign every field the moment the requested
        field list changes. Keying by ``result.fields`` keeps the mapping honest.
        """
        if result.error_code != "0":
            raise DataSourceError(
                f"baostock {what} failed for {code}: {result.error_msg}",
                {"error_code": result.error_code, "code": code},
            )
        fields = list(result.fields)
        rows: list[dict[str, str]] = []
        while result.next():
            rows.append(dict(zip(fields, result.get_row_data())))
        return rows

    # ── bars ───────────────────────────────────────────────────────

    def get_bars(
        self,
        code: str,
        start: date,
        end: date,
        freq: Freq = Freq.DAY,
    ) -> list[Bar]:
        """Fetch unadjusted bars for one security.

        See the module docstring for the verified unit conventions: volume is in
        shares and amount is in CNY, so no rescaling happens here.
        """
        self.require(Capability.BARS, freq)
        bs = self._login()
        security = parse(code)
        bao_code = security.to_baostock()

        result = bs.query_history_k_data_plus(
            bao_code,
            DAILY_FIELDS,
            start_date=start.isoformat(),
            end_date=end.isoformat(),
            frequency=FREQ_CODES[freq],
            adjustflag=ADJUST_RAW,
        )
        rows = self._drain(result, "get_bars", bao_code)

        bars: list[Bar] = []
        for row in rows:
            close = _to_float(row["close"])
            if close is None:
                # No price at all: nothing meaningful to record for this day.
                continue
            context = f"{bao_code} on {row['date']}"
            suspended = row.get("tradestatus") == SUSPENDED
            bars.append(
                Bar(
                    freq=freq,
                    code=security.symbol,
                    ts=datetime.fromisoformat(row["date"]),
                    open=_require_float(row["open"], "open", context),
                    high=_require_float(row["high"], "high", context),
                    low=_require_float(row["low"], "low", context),
                    close=close,
                    volume=_volume_like(
                        row["volume"], suspended=suspended, field="volume", context=context
                    ),
                    amount=_volume_like(
                        row["amount"], suspended=suspended, field="amount", context=context
                    ),
                    is_suspended=suspended,
                    pct_change=_percent_to_fraction(row.get("pctChg", "")),
                    source=self.name,
                )
            )
        bars.sort(key=lambda bar: bar.ts)
        return bars

    # ── factors ────────────────────────────────────────────────────

    def get_factors(self, code: str, start: date, end: date) -> list[AdjustFactor]:
        """Return the back-adjustment factor for every trading day in range.

        The result is forward-filled, not sparse: each trading day in
        ``[start, end]`` gets the factor of the most recent corporate action at
        or before it. Days preceding the first recorded action take
        ``_FACTOR_BASE``.
        """
        self.require(Capability.FACTORS)
        bs = self._login()
        security = parse(code)
        bao_code = security.to_baostock()

        # Deliberately scan from the epoch: starting at ``start`` would leave the
        # range's opening days with no preceding action, and back-filling from
        # the first in-window action would apply a dividend before it happened.
        result = bs.query_adjust_factor(
            code=bao_code, start_date=_EPOCH.isoformat(), end_date=end.isoformat()
        )
        rows = self._drain(result, "get_factors", bao_code)

        actions: list[tuple[date, float]] = []
        for row in rows:
            factor = _to_float(row["backAdjustFactor"])
            if factor is None:
                continue
            actions.append((_to_date(row["dividOperateDate"]), factor))
        actions.sort(key=lambda item: item[0])
        actions, artifacts = enforce_monotonic_chain(actions)
        if artifacts:
            # Not silent: a repaired step means the source's chain was broken,
            # which is worth knowing about even though it has been corrected.
            logger.warning(
                "baostock_factor_chain_repaired",
                code=bao_code,
                artifacts=len(artifacts),
                first_day=artifacts[0].day.isoformat(),
                largest_step=min(a.step for a in artifacts),
            )

        return [
            AdjustFactor(
                code=security.symbol,
                ts=day,
                factor=_factor_on(actions, day),
                source=self.name,
            )
            for day in self._trading_days(bs, start, end)
        ]

    def _trading_days(self, bs: Any, start: date, end: date) -> list[date]:
        result = bs.query_trade_dates(
            start_date=start.isoformat(), end_date=end.isoformat()
        )
        rows = self._drain(result, "query_trade_dates", f"{start}..{end}")
        return [_to_date(row["calendar_date"]) for row in rows if row["is_trading_day"] == "1"]

    # ── calendar ───────────────────────────────────────────────────

    def get_calendar(self, start: date, end: date, freq: Freq = Freq.DAY) -> list[datetime]:
        """Fetch the trading calendar. Daily and intraday share one calendar."""
        self.require(Capability.CALENDAR, freq)
        bs = self._login()
        days = self._trading_days(bs, start, end)
        return [datetime.combine(day, datetime.min.time()) for day in days]

    # ── instruments ────────────────────────────────────────────────

    def get_instruments(self, on: date | None = None) -> list[Instrument]:
        """Intentionally unsupported — see :meth:`resolve_listing_spans`.

        Listing spans are only available one code at a time, so materializing a
        universe of a few thousand securities would take thousands of round
        trips. Rather than declare a capability it cannot serve cheaply, this
        provider leaves ``INSTRUMENTS`` out of :meth:`capabilities` and offers
        two bounded alternatives: :meth:`get_index_constituents` for a defined
        universe, and :meth:`resolve_listing_spans` for codes the caller has
        already narrowed down.
        """
        raise DataSourceError(
            "baostock cannot serve a whole-market instrument list: listing spans "
            "require one query per code. Use get_index_constituents() to pick a "
            "universe, then resolve_listing_spans() to fill in its date ranges.",
            {"provider": self.name},
        )

    def get_index_constituents(self, index: str) -> list[str]:
        """Return the canonical codes making up an index.

        Only the *current* membership is available — BaoStock does not publish
        historical constituent changes — so a backtest over past periods carries
        a survivorship bias that must be stated wherever its results appear.
        """
        endpoint = {
            "csi300": "query_hs300_stocks",
            "hs300": "query_hs300_stocks",
            "csi500": "query_zz500_stocks",
            "zz500": "query_zz500_stocks",
            "sse50": "query_sz50_stocks",
            "sz50": "query_sz50_stocks",
        }.get(index.lower())
        if endpoint is None:
            raise DataSourceError(
                f"unknown index {index!r}; expected one of csi300, csi500, sse50",
                {"index": index},
            )

        bs = self._login()
        result = getattr(bs, endpoint)()
        rows = self._drain(result, endpoint, index)
        return [parse(row["code"]).symbol for row in rows]

    def resolve_listing_spans(self, codes: Iterable[str]) -> list[Instrument]:
        """Resolve listing spans for an explicit, bounded set of codes.

        One query per code, so callers should pass a universe they have already
        narrowed (an index's constituents, say) rather than the whole market.
        Codes whose listing date cannot be resolved are skipped.

        Args:
            codes: Security codes in any accepted spelling.

        Returns:
            One instrument per resolvable code, with ``end_date`` set to its
            delisting date, or today when still listed.
        """
        bs = self._login()
        # A listing span is measured in exchange calendar dates, not instants,
        # so a naive local date is the right shape here.
        today = date.today()  # noqa: DTZ011
        instruments: list[Instrument] = []

        for raw in codes:
            security = parse(raw)
            rows = self._drain(
                bs.query_stock_basic(code=security.to_baostock()),
                "query_stock_basic",
                security.to_baostock(),
            )
            if not rows:
                continue
            row = rows[0]
            ipo = row["ipoDate"].strip()
            if not ipo:
                continue
            delisted = row["outDate"].strip()
            instruments.append(
                Instrument(
                    code=security.symbol,
                    name=row["code_name"],
                    start_date=_to_date(ipo),
                    end_date=_to_date(delisted) if delisted else today,
                )
            )
        return instruments
