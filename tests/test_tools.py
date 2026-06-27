"""Tests for Agent tools."""

import pytest

from src.core.backtest_engine import BacktestEngine
from src.core.factor_store import FactorStore
from src.core.strategy_compiler import StrategyCompiler
from src.tools.factor_tools import create_factor, search_factors
from src.tools.strategy_tools import compose_strategy
from src.tools.storage_tools import StrategyStore, list_strategies, load_strategy, save_strategy


class TestFactorTools:
    """Test factor tool functions."""

    def test_search_factors(self, factor_store_with_builtins):
        results = search_factors("动量", factor_store_with_builtins)
        assert len(results) > 0
        assert all("id" in r for r in results)

    def test_create_factor(self, factor_store):
        result = create_factor(
            id="test_factor",
            name="测试因子",
            description="用于测试的因子",
            category="momentum",
            formula="Ref($close, 0) / Ref($close, 20) - 1",
            factor_store=factor_store,
            tags=["测试"],
        )
        assert result["status"] == "created"
        assert result["id"] == "test_factor"


class TestStrategyTools:
    """Test strategy tool functions."""

    def test_compose_strategy(self):
        result = compose_strategy(
            name="测试策略",
            factor_ids=["momentum_3m"],
            start_date="2020-01-01",
            end_date="2024-12-31",
        )
        assert result["status"] == "composed"
        assert result["name"] == "测试策略"


class TestStorageTools:
    """Test storage tool functions."""

    def test_save_and_load(self, strategy_store):
        config = {"name": "test", "factor_ids": ["momentum_3m"]}
        save_result = save_strategy("test_strategy", config, strategy_store)
        assert save_result["status"] == "saved"

        load_result = load_strategy(save_result["strategy_id"], strategy_store)
        assert load_result["status"] == "loaded"
        assert load_result["name"] == "test_strategy"

    def test_list_strategies(self, strategy_store):
        save_strategy("strat1", {"factor_ids": ["a"]}, strategy_store)
        save_strategy("strat2", {"factor_ids": ["b"]}, strategy_store)
        result = list_strategies(strategy_store)
        assert len(result) == 2


class TestVersionChain:
    """Test strategy version chain."""

    def test_save_with_version(self, strategy_store):
        config = {"name": "test", "factor_ids": ["momentum_3m"]}
        result = save_strategy("v1", config, strategy_store, version=1)
        assert result["status"] == "saved"

    def test_create_new_version(self, strategy_store):
        config = {"name": "test", "factor_ids": ["momentum_3m"]}
        v1 = save_strategy("test", config, strategy_store, version=1)
        v2 = save_strategy("test", config, strategy_store, version=2, parent_id=v1["strategy_id"])
        assert v2["status"] == "saved"

        chain = strategy_store.get_version_chain(v2["strategy_id"])
        assert len(chain) == 2
        assert chain[0]["version"] == 1
        assert chain[1]["version"] == 2

    def test_get_latest_version(self, strategy_store):
        config = {"name": "test", "factor_ids": ["momentum_3m"]}
        save_strategy("test", config, strategy_store, version=1)
        save_strategy("test", config, strategy_store, version=2)
        latest = strategy_store.get_latest_version("test")
        assert latest["version"] == 2

    def test_backward_compatibility(self, strategy_store):
        """Old strategies without version fields still work."""
        config = {"name": "old", "factor_ids": ["a"]}
        save_strategy("old", config, strategy_store)
        loaded = strategy_store.get_latest_version("old")
        assert loaded["version"] == 1
        assert loaded.get("parent_id") is None


# ── Fixtures ───────────────────────────────────────────────────────


@pytest.fixture
def factor_store(tmp_path):
    from src.core.factor_store import FactorStore
    return FactorStore(db_path=str(tmp_path / "test.db"), chroma_path=str(tmp_path / "chroma"))


@pytest.fixture
def factor_store_with_builtins(factor_store):
    factor_store.load_builtin_factors()
    return factor_store


@pytest.fixture
def strategy_store(tmp_path):
    return StrategyStore(db_path=str(tmp_path / "strategies.db"))
