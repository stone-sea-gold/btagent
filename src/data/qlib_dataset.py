"""Resolve the Qlib dataset the backtest engine should run against.

The data layer exports a Qlib dataset — see :mod:`src.data.qlib_export` — and
the warehouse-synced window is authoritative for coverage. That export is the
only source: the retired official-download path is gone, so the engine cannot
silently read a dataset the warehouse did not produce.

Initialization lives here too because Qlib keeps one module-global provider:
whatever calls ``qlib.init`` pins the whole process to that directory, so every
consumer must resolve the dataset the same way or an earlier caller can strand
later ones on a missing path.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Any

from src.config import settings
from src.exceptions import BacktestError
from src.logging import get_logger

if TYPE_CHECKING:
    import pandas as pd

logger = get_logger(__name__)


def provider_uri() -> Path | None:
    """The exported Qlib dataset directory, or ``None`` when it is absent."""
    candidate = Path(settings.qlib_export_path)
    if (candidate / "calendars").joinpath("day.txt").exists():
        return candidate
    return None


def ensure_init() -> None:
    """Initialize Qlib against the resolved dataset, idempotently.

    Raises:
        BacktestError: no dataset exists yet — the message points at the
            sync/export pipeline, not the retired download command.
    """
    uri = provider_uri()
    if uri is None:
        raise BacktestError(
            "本地没有 Qlib 数据集。请先同步行情再导出："
            "`python cli.py --sync-data --index csi300 --years 5` "
            "然后 `python cli.py --export-qlib`。",
            details={"error_type": "no_data", "export_path": settings.qlib_export_path},
        )
    import qlib

    # An initialized process cannot be re-pointed, so a refusal here simply
    # means an earlier init pinned the same directory.
    qlib.init(provider_uri=str(uri), region="cn")


def calendar_days(start: str | None = None, end: str | None = None) -> list[str]:
    """The resolved dataset's trading calendar, as ``YYYY-MM-DD`` strings."""
    ensure_init()

    from qlib.data import D

    days = D.calendar(start_time=start or "1990-01-01", end_time=end or "2100-12-31")
    return [str(day)[:10] for day in days]


def calendar_start_end() -> tuple[date, date]:
    """First and last days of the resolved dataset's calendar.

    Raises:
        BacktestError: when no dataset exists or its calendar is empty.
    """
    days = calendar_days()
    if not days:
        raise BacktestError(
            "Qlib 日历数据为空。请运行 `python cli.py --sync-data` "
            "并 `python cli.py --export-qlib` 导出数据。",
            details={"error_type": "data_empty"},
        )
    return date.fromisoformat(days[0]), date.fromisoformat(days[-1])


def covered(date_str: str) -> bool:
    """Whether ``date_str`` falls inside the resolved calendar."""
    start, end = calendar_start_end()
    return start <= date.fromisoformat(date_str) <= end


def features(instruments: list[str], fields: list[str], start: str, end: str) -> pd.DataFrame:
    """Read features straight from the resolved dataset.

    The wrapper belongs here rather than at each call site so a caller cannot
    accidentally read through a provider pointing at a missing directory.
    """
    ensure_init()

    from qlib.data import D

    return D.features(instruments, fields, start, end)


def coverage() -> dict[str, Any]:
    """Coverage summary for diagnostics and agent tools."""
    start, end = calendar_start_end()
    return {"start": start.isoformat(), "end": end.isoformat()}
