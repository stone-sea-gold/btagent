"""Tests for the data-coverage tool.

The warehouse summary is JSON for the model, and ``MarketStore.coverage`` hands
back ``date`` objects.  A fake store that returned strings once hid a
``TypeError`` at that boundary, so these tests push real ``date`` objects
through the tool and assert on the serialized payload.
"""

import json
from datetime import date
from typing import Self

import pytest

from src.config import settings
from src.data import store as store_mod
from src.exceptions import BacktestError
from src.tools import data_tools


class _FakeStore:
    """Stand-in returning the same value types the real store does."""

    def __init__(self, *args, **kwargs) -> None:
        pass

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> bool:
        return False

    def coverage(self) -> dict:
        return {
            "freq": "day",
            "bars": 75_998,
            "codes": 299,
            "first_date": date(2020, 1, 2),
            "last_date": date(2024, 12, 31),
            "factor_rows": 76_722,
            "calendar_days": 1212,
        }


_NO_DATA = {
    "start_date": None,
    "end_date": None,
    "is_stale": True,
    "days_behind": None,
    "status": "no_data",
}


def _stub_dataset(monkeypatch, *, warehouse_db, coverage=None, init=None) -> None:
    """Point the tool at a fake store, a stub calendar and a chosen db path."""
    monkeypatch.setattr(settings, "market_data_db", str(warehouse_db))
    monkeypatch.setattr(store_mod, "MarketStore", _FakeStore)
    monkeypatch.setattr(
        "src.data.qlib_dataset.ensure_init", init if init is not None else (lambda: None)
    )
    monkeypatch.setattr(
        data_tools._calendar,
        "get_data_coverage",
        lambda: coverage
        or {
            "start_date": "2020-01-02",
            "end_date": "2024-12-31",
            "is_stale": True,
            "days_behind": 626,
            "status": "success",
        },
    )


@pytest.fixture
def warehouse_db(tmp_path):
    """An existing (empty) database file, so the existence guard passes."""
    path = tmp_path / "market.duckdb"
    path.write_bytes(b"")
    return path


class TestWarehouseSummary:
    def test_dates_are_serialized(self, monkeypatch, warehouse_db):
        """Regression: a raw ``date`` is not JSON serializable."""
        _stub_dataset(monkeypatch, warehouse_db=warehouse_db)

        payload = json.loads(data_tools.check_data_coverage())

        assert payload["status"] == "success"
        assert payload["warehouse"]["first_date"] == "2020-01-02"
        assert payload["warehouse"]["last_date"] == "2024-12-31"

    def test_totals_are_reported(self, monkeypatch, warehouse_db):
        _stub_dataset(monkeypatch, warehouse_db=warehouse_db)

        warehouse = json.loads(data_tools.check_data_coverage())["warehouse"]

        assert warehouse["bars"] == 75_998
        assert warehouse["codes"] == 299
        assert warehouse["factor_rows"] == 76_722

    def test_dataset_window_is_reported_alongside(self, monkeypatch, warehouse_db):
        _stub_dataset(monkeypatch, warehouse_db=warehouse_db)

        payload = json.loads(data_tools.check_data_coverage())

        assert payload["data_start_date"] == "2020-01-02"
        assert payload["data_end_date"] == "2024-12-31"
        assert payload["days_behind"] == 626

    def test_missing_warehouse_is_reported_not_created(self, monkeypatch, tmp_path):
        """A diagnostic read must not create the database file."""
        missing = tmp_path / "absent" / "market.duckdb"
        _stub_dataset(monkeypatch, warehouse_db=missing, coverage=_NO_DATA)

        payload = json.loads(data_tools.check_data_coverage())

        assert payload["warehouse"] == {"status": "no_warehouse"}
        assert not missing.exists()


class TestMissingDataset:
    def test_ensure_init_failure_still_reports_no_data(self, monkeypatch, warehouse_db):
        """A missing dataset is a reportable fact, not an error payload."""

        def _raise() -> None:
            raise BacktestError("no dataset")

        _stub_dataset(monkeypatch, warehouse_db=warehouse_db, coverage=_NO_DATA, init=_raise)

        payload = json.loads(data_tools.check_data_coverage())

        assert payload["status"] == "no_data"
        assert "error" not in payload

    def test_stale_warning_points_at_the_current_pipeline(self, monkeypatch, warehouse_db):
        _stub_dataset(monkeypatch, warehouse_db=warehouse_db)

        warning = json.loads(data_tools.check_data_coverage())["warning"]

        assert "--sync-data" in warning
        assert "--init-data" not in warning
