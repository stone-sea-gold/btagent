"""Tests for the background sync job manager.

The pipeline itself (provider, warehouse, exporter) is replaced with fakes: what
matters here is the job contract the UI polls — that a run reports progress,
finishes with counts, surfaces failures instead of raising them into a thread,
and refuses to start a second writer over the same warehouse.
"""

import threading
import time
from typing import Self

import pytest

from src.core import sync_jobs
from src.exceptions import DataSourceError

CODES = ["600519.SH", "000001.SZ"]


class _Result:
    codes_synced = 2
    codes_skipped = 0
    codes_failed = 0
    bars_written = 500
    factors_written = 500
    calendar_days = 0


class _FakeStore:
    def __init__(self, *args, **kwargs) -> None:
        pass

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> bool:
        return False


@pytest.fixture
def pipeline(monkeypatch) -> dict:
    """Replace the sync pipeline, recording what the job asked for."""
    seen: dict = {}

    def fake_sync(store, provider, selected, start, end, *, progress=None):
        seen["selected"] = list(selected)
        seen["start"], seen["end"] = start, end
        if progress:
            for index, code in enumerate(selected, start=1):
                progress(index, len(selected), code, 250)
        return _Result()

    def fake_export(*args, **kwargs) -> dict:
        seen["exported"] = True
        return {"days": 1212}

    monkeypatch.setattr(sync_jobs, "MarketStore", _FakeStore)
    # ``PROVIDERS`` backs the early source validation; ``get_provider`` is what
    # the worker actually syncs with now that sessions are shared.
    monkeypatch.setattr(sync_jobs, "PROVIDERS", {"fake": lambda: "provider"})
    monkeypatch.setattr(sync_jobs, "get_provider", lambda name: "provider")
    monkeypatch.setattr(
        sync_jobs, "resolve_codes", lambda p, index=None, codes=None: list(CODES)
    )
    monkeypatch.setattr(sync_jobs, "sync_codes", fake_sync)
    monkeypatch.setattr(sync_jobs, "sync_calendar", lambda store, provider, s, e: 250)
    monkeypatch.setattr(sync_jobs, "write_qlib_dataset", fake_export)
    return seen


def _settle(job: sync_jobs.SyncJob, timeout: float = 5.0) -> sync_jobs.SyncJob:
    """Wait for a job to leave the running state."""
    deadline = time.time() + timeout
    while job.status == "running" and time.time() < deadline:
        time.sleep(0.01)
    return job


class TestStart:
    def test_unknown_source_is_rejected(self, pipeline):
        manager = sync_jobs.SyncJobManager()

        with pytest.raises(DataSourceError, match="unknown data source"):
            manager.start(source="yahoo", index="csi300")

    def test_a_second_writer_is_refused_while_one_runs(self, pipeline, monkeypatch):
        release = threading.Event()

        def blocking_sync(store, provider, selected, start, end, *, progress=None):
            release.wait(5)
            return _Result()

        monkeypatch.setattr(sync_jobs, "sync_codes", blocking_sync)
        manager = sync_jobs.SyncJobManager()
        first = manager.start(source="fake", index="csi300")

        with pytest.raises(DataSourceError, match="已有同步任务"):
            manager.start(source="fake", index="csi300")

        release.set()
        _settle(first)


class TestRun:
    def test_job_finishes_with_counts(self, pipeline):
        manager = sync_jobs.SyncJobManager()

        job = _settle(manager.start(source="fake", index="csi300"))

        assert job.status == "done"
        assert job.phase == "finished"
        assert job.codes_synced == 2
        assert job.bars_written == 500
        assert job.factors_written == 500
        assert job.finished_at is not None

    def test_export_runs_so_the_dataset_is_not_left_behind(self, pipeline):
        """The warehouse can be current while the dataset a backtest reads is not."""
        manager = sync_jobs.SyncJobManager()

        job = _settle(manager.start(source="fake", index="csi300"))

        assert pipeline.get("exported") is True
        assert job.dataset_days == 1212

    def test_progress_is_reported_per_code(self, pipeline):
        manager = sync_jobs.SyncJobManager()

        job = _settle(manager.start(source="fake", index="csi300"))

        assert job.total == len(CODES)
        assert job.completed == len(CODES)
        assert job.progress == 1.0
        assert job.current_code == CODES[-1]

    def test_a_failure_is_reported_not_raised(self, pipeline, monkeypatch):
        """An exception on the worker thread must land on the job, not vanish."""
        def explode(*args, **kwargs):
            raise RuntimeError("provider exploded")

        monkeypatch.setattr(sync_jobs, "sync_codes", explode)
        manager = sync_jobs.SyncJobManager()

        job = _settle(manager.start(source="fake", index="csi300"))

        assert job.status == "error"
        assert "provider exploded" in job.error
        assert job.finished_at is not None


class TestQueries:
    def test_get_and_latest_find_the_job(self, pipeline):
        manager = sync_jobs.SyncJobManager()

        job = _settle(manager.start(source="fake", index="csi300"))

        assert manager.get(job.id) is job
        assert manager.latest() is job
        assert manager.get("nope") is None

    def test_nothing_running_once_settled(self, pipeline):
        manager = sync_jobs.SyncJobManager()

        _settle(manager.start(source="fake", index="csi300"))

        assert manager.running() is None

    def test_empty_manager_reports_nothing(self):
        manager = sync_jobs.SyncJobManager()

        assert manager.latest() is None
        assert manager.running() is None

    def test_snapshot_is_a_plain_dict_with_progress(self, pipeline):
        manager = sync_jobs.SyncJobManager()

        job = _settle(manager.start(source="fake", index="csi300"))
        snapshot = job.snapshot()

        assert snapshot["id"] == job.id
        assert snapshot["progress"] == 1.0
        assert "status" in snapshot
