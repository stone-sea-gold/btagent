"""Background market-data sync jobs.

A sync hits an external service and can run for minutes, so it is started on a
worker thread and polled by the UI rather than awaited inside a request. Records
live in this process's memory, which is enough because the API runs a single
uvicorn worker; restarting the server loses the job records, while the data an
interrupted job already wrote stays committed in the warehouse.

A job does the whole pipeline — sync the warehouse, then re-export the dataset
the backtest engine reads — because the two drift apart: the warehouse can be
current while the exported dataset is a year behind, and a backtest would then
silently run on the older window.
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any

from src.config import settings
from src.data.providers import PROVIDERS, get_provider
from src.data.qlib_export import write_qlib_dataset
from src.data.store import MarketStore
from src.data.sync import resolve_codes, sync_calendar, sync_codes
from src.exceptions import DataSourceError
from src.logging import get_logger

logger = get_logger(__name__)


def _utc_now() -> str:
    """ISO-8601 UTC, the timestamp shape the rest of the app stores."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class SyncJob:
    """Progress and outcome of one background sync."""

    id: str
    status: str = "running"  # running | done | error
    phase: str = "starting"  # starting | syncing | exporting | finished
    total: int = 0
    completed: int = 0
    current_code: str = ""
    codes_synced: int = 0
    codes_skipped: int = 0
    codes_failed: int = 0
    bars_written: int = 0
    factors_written: int = 0
    calendar_days: int = 0
    dataset_days: int = 0
    started_at: str = field(default_factory=_utc_now)
    finished_at: str | None = None
    error: str = ""

    @property
    def progress(self) -> float:
        """Fraction of the requested codes handled so far."""
        return round(self.completed / self.total, 4) if self.total else 0.0

    def snapshot(self) -> dict[str, Any]:
        """A plain dict for the API, safe to read while the worker mutates."""
        return {**vars(self), "progress": self.progress}


class SyncJobManager:
    """Starts sync jobs and answers questions about them."""

    def __init__(self) -> None:
        self._jobs: dict[str, SyncJob] = {}
        self._order: list[str] = []
        self._lock = threading.Lock()

    # ── queries ────────────────────────────────────────────────────

    def get(self, job_id: str) -> SyncJob | None:
        with self._lock:
            return self._jobs.get(job_id)

    def latest(self) -> SyncJob | None:
        with self._lock:
            return self._jobs[self._order[-1]] if self._order else None

    def running(self) -> SyncJob | None:
        with self._lock:
            for job_id in reversed(self._order):
                job = self._jobs[job_id]
                if job.status == "running":
                    return job
        return None

    # ── start ──────────────────────────────────────────────────────

    def start(
        self,
        *,
        index: str = "",
        codes: list[str] | None = None,
        years: int = settings.years_sync_default,
        source: str = "",
    ) -> SyncJob:
        """Register a job and run it on a worker thread.

        Raises:
            DataSourceError: the source name is unknown, or a sync is already
                running — two writers would fight over the same warehouse.
        """
        name = source.strip() or settings.data_source_priority.split(",")[0].strip()
        if name not in PROVIDERS:
            raise DataSourceError(
                f"unknown data source {name!r}; available: {sorted(PROVIDERS)}"
            )
        active = self.running()
        if active is not None:
            raise DataSourceError(
                f"已有同步任务在执行（{active.id}）", {"job_id": active.id}
            )

        job = SyncJob(id=uuid.uuid4().hex[:12])
        with self._lock:
            self._jobs[job.id] = job
            self._order.append(job.id)

        threading.Thread(
            target=self._run,
            args=(job, name, index.strip(), list(codes or []), years),
            name=f"sync-{job.id}",
            daemon=True,
        ).start()
        return job

    # ── worker ─────────────────────────────────────────────────────

    def _run(
        self, job: SyncJob, source: str, index: str, codes: list[str], years: int
    ) -> None:
        try:
            end = date.today()  # noqa: DTZ011 - a trading window, not an instant
            start = end - timedelta(days=365 * years)

            # Connecting is its own phase: BaoStock's login alone costs over a
            # minute here, and without it the UI would sit on "syncing 0/N" with
            # no way to tell that apart from a stalled transfer. The provider is
            # shared, so only the first run after startup pays that cost.
            job.phase = "connecting"
            provider = get_provider(source)

            with MarketStore() as store:
                job.phase = "syncing"
                selected = resolve_codes(
                    provider, index=index or None, codes=codes or None
                )
                job.total = len(selected)

                def on_progress(done: int, total: int, code: str, written: int) -> None:
                    job.completed = done
                    job.total = total
                    job.current_code = code

                result = sync_codes(
                    store, provider, selected, start, end, progress=on_progress
                )
                result.calendar_days = sync_calendar(store, provider, start, end)

                job.codes_synced = result.codes_synced
                job.codes_skipped = result.codes_skipped
                job.codes_failed = result.codes_failed
                job.bars_written = result.bars_written
                job.factors_written = result.factors_written
                job.calendar_days = result.calendar_days

                job.phase = "exporting"
                counts = write_qlib_dataset(
                    store,
                    settings.qlib_export_path,
                    exclude_from_universe=[settings.benchmark_code],
                )
                job.dataset_days = counts["days"]

            job.phase = "finished"
            job.finished_at = _utc_now()
            # Status is assigned last so a poller that sees a settled job always
            # sees its final fields too, rather than a half-populated record.
            job.status = "done"
            logger.info(
                "sync_job_done",
                job=job.id,
                codes_synced=job.codes_synced,
                bars_written=job.bars_written,
                dataset_days=job.dataset_days,
            )
        except Exception as exc:  # noqa: BLE001 - a failed job must be reportable
            job.error = str(exc)
            job.finished_at = _utc_now()
            job.status = "error"
            logger.error("sync_job_failed", job=job.id, error=str(exc))


#: Process-wide manager; see the module docstring for why in-memory is enough.
manager = SyncJobManager()
