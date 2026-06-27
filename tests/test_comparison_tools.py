"""Tests for comparison and update tools — written BEFORE implementation (TDD)."""

import pytest

from src.tools.comparison_tools import compare_strategies, update_strategy
from src.tools.storage_tools import StrategyStore, save_strategy


class TestCompareStrategies:
    """Test strategy comparison."""

    def test_compare_two_strategies(self, store_with_strategies):
        store, s1, s2 = store_with_strategies
        result = compare_strategies([s1["strategy_id"], s2["strategy_id"]], store)
        assert result["status"] == "success"
        assert len(result["strategies"]) == 2
        assert "factor_diff" in result

    def test_compare_nonexistent(self, store):
        result = compare_strategies(["nonexistent_1", "nonexistent_2"], store)
        assert result["status"] == "error"

    def test_compare_single_strategy(self, store_with_strategies):
        store, s1, _ = store_with_strategies
        result = compare_strategies([s1["strategy_id"]], store)
        assert result["status"] == "success"
        assert len(result["strategies"]) == 1


class TestUpdateStrategy:
    """Test strategy update (creates new version)."""

    def test_update_creates_new_version(self, store_with_strategies):
        store, s1, _ = store_with_strategies
        result = update_strategy(
            strategy_id=s1["strategy_id"],
            modifications={"max_holding": 20},
            store=store,
        )
        assert result["status"] == "updated"
        assert result["version"] == 2
        assert result["parent_id"] == s1["strategy_id"]

    def test_update_preserves_chain(self, store_with_strategies):
        store, s1, _ = store_with_strategies
        # Create v2
        v2 = update_strategy(
            strategy_id=s1["strategy_id"],
            modifications={"max_holding": 20},
            store=store,
        )
        # Create v3 from v2
        v3 = update_strategy(
            strategy_id=v2["strategy_id"],
            modifications={"rebalance_freq": "weekly"},
            store=store,
        )
        assert v3["version"] == 3
        chain = store.get_version_chain(v3["strategy_id"])
        assert len(chain) == 3

    def test_update_nonexistent(self, store):
        result = update_strategy("nonexistent", {"max_holding": 20}, store)
        assert result["status"] == "error"


# ── Fixtures ───────────────────────────────────────────────────────


@pytest.fixture
def store(tmp_path):
    return StrategyStore(db_path=str(tmp_path / "strategies.db"), chroma_path=str(tmp_path / "chroma"))


@pytest.fixture
def store_with_strategies(store):
    config1 = {
        "name": "动量策略",
        "factor_ids": ["momentum_3m"],
        "start_date": "2020-01-01",
        "end_date": "2024-12-31",
        "selection_rule": "top_k",
        "selection_params": {"k": 10},
        "weight_scheme": "equal",
        "rebalance_freq": "monthly",
        "universe": "csi300",
        "max_holding": 10,
    }
    config2 = {
        "name": "价值策略",
        "factor_ids": ["ep_ratio"],
        "start_date": "2020-01-01",
        "end_date": "2024-12-31",
        "selection_rule": "top_k",
        "selection_params": {"k": 15},
        "weight_scheme": "equal",
        "rebalance_freq": "monthly",
        "universe": "csi300",
        "max_holding": 15,
    }
    s1 = save_strategy("动量策略", config1, store, agent_summary="动量因子进攻型策略")
    s2 = save_strategy("价值策略", config2, store, agent_summary="价值因子防守型策略")
    return store, s1, s2
