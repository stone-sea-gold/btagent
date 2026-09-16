"""Tests for the market-data adapters on the agent surface.

The adapters are thin shims over the warehouse pipeline, so these tests focus
on the conversation-facing contract: argument shaping (a comma-joined code
string → a list, a relative window in years → concrete dates), how a failure is
reported back, and that a successful call yields a JSON payload the model can
quote straight into the chat.
"""
import json
from collections.abc import Callable
from datetime import datetime
from typing import Any

import pytest

from src.agent.adapters.data import register
from src.agent.deps import AgentDeps
from src.agent.registry import ToolRegistry
from src.data import store as store_mod
from src.data import sync as sync_mod
from src.exceptions import DataSourceError


def _deps() -> AgentDeps:
    """AgentDeps with placeholder services: registration only closes over."""
    return AgentDeps(
        factor_store=None, strategy_compiler=None, backtest_engine=None,
        strategy_store=None, session_store=None,
    )


@pytest.fixture
def store_record() -> dict[str, int]:
    return {"bars": 0, "factors": 0, "calendar": 0}


@pytest.fixture
def tools(monkeypatch, store_record) -> dict[str, Callable[..., str]]:
    """Build the adapter with the pipeline's storage layer stubbed."""

    class FakeStore:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def __enter__(self) -> "FakeStore":
            return self

        def __exit__(self, *exc: object) -> bool:
            return False

        def upsert_bars(self, bars: list) -> int:
            store_record["bars"] += len(bars)
            return len(bars)

        def upsert_factors(self, factors: list) -> int:
            store_record["factors"] += len(factors)
            return len(factors)

        def upsert_calendar(self, freq: str, days: list) -> int:
            store_record["calendar"] += len(days)
            return len(days)

        def synced_span(self, code: str, freq: str = "day") -> tuple | None:
            return None

        def record_sync(self, code, freq, start, end, rows_written: int) -> None:
            return None

        def coverage(self) -> dict[str, Any]:
            return {
                "bars": 74_000,
                "codes": 298,
                "first_date": "2020-01-02",
                "last_date": "2024-12-31",
            }

    class FakeProvider:
        name = "fake"

        def get_bars(self, code, start, end, freq="day"):
            return [object(), object()]

        def get_factors(self, code, start, end):
            return [object()]

        def supports(self, capability, freq=None) -> bool:
            return True

        def get_calendar(self, start, end, freq="day"):
            return [_d for _d in (datetime(2024, 1, 2), datetime(2024, 1, 3))]

        def get_instruments(self, on=None):
            return []

        def get_index_constituents(self, index: str) -> list[str]:
            return ["600519.SH", "000001.SZ"]

    monkeypatch.setattr(store_mod, "MarketStore", FakeStore)
    monkeypatch.setattr(sync_mod, "MarketStore", FakeStore)
    monkeypatch.setattr("src.data.providers.PROVIDERS", {"fake": lambda: FakeProvider()})

    registry = ToolRegistry()
    register(registry, _deps())
    return registry.dispatch()


def _reshape(payload: str) -> dict[str, Any]:
    return json.loads(payload)


class TestGetCoverage:
    def test_reports_what_the_warehouse_holds(self, tools):
        payload = _reshape(tools["_get_data_coverage"]())

        assert payload["status"] == "success"
        assert payload["bars"] == 74_000
        assert payload["first_date"] == "2020-01-02"


class TestSyncTool:
    def test_index_name_resolves_the_universe(self, tools):
        payload = _reshape(tools["_sync_market_data"](index="csi300", source="fake"))

        assert payload["status"] == "success"
        assert payload["codes_requested"] == 2
        assert payload["bars_written"] == 4
        assert payload["factors_written"] == 2

    def test_codes_string_is_parsed_canonically(self, tools):
        payload = _reshape(tools["_sync_market_data"](codes=" 600519.SH,000001.SZ", source="fake"))

        assert payload["status"] == "success"
        assert payload["codes_requested"] == 2
        assert payload["bars_written"] == 4

    def test_unknown_source_is_named(self, tools):
        with pytest.raises(DataSourceError, match="unknown data source"):
            tools["_sync_market_data"](source="yahoo")


class TestExportTool:
    def test_reports_the_dataset_shape(self, tools, monkeypatch):
        captured: dict[str, Any] = {}

        monkeypatch.setattr(
            "src.data.qlib_export.write_qlib_dataset",
            lambda *a, **kw: {"instruments": 298, "features": 299, "days": 1212, "fields": 7},
        )
        payload = _reshape(tools["_export_qlib_dataset"]())

        assert payload["status"] == "success"
        assert payload["instruments"] == 298
        assert payload["days"] == 1212
