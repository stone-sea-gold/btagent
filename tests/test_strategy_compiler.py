"""Tests for StrategyCompiler — written BEFORE implementation (TDD).

Tests cover:
- Compile valid StrategyConfig to Qlib strategy object
- Handle missing/invalid factors
- Handle edge cases (empty factor list, extreme params)
"""

import pytest

from src.core.models import (
    FactorCategory,
    FactorCreate,
    RebalanceFreq,
    SelectionRule,
    StrategyConfig,
    WeightScheme,
)
from src.core.strategy_compiler import StrategyCompileError, StrategyCompiler


class TestStrategyCompiler:
    """Test strategy compilation from config to Qlib objects."""

    def test_compile_basic_strategy(self, compiler, sample_factors_in_store):
        """Compile a basic strategy with momentum factor."""
        config = StrategyConfig(
            name="test_momentum",
            factor_ids=["momentum_3m"],
            selection_rule=SelectionRule.TOP_K,
            selection_params={"k": 10},
            weight_scheme=WeightScheme.EQUAL,
            rebalance_freq=RebalanceFreq.MONTHLY,
            universe="csi300",
            start_date="2020-01-01",
            end_date="2024-12-31",
        )
        result = compiler.compile(config)
        assert result is not None
        assert result["strategy_config"] == config
        assert "qlib_strategy" in result

    def test_compile_multi_factor(self, compiler, sample_factors_in_store):
        """Compile a strategy with multiple factors."""
        config = StrategyConfig(
            name="multi_factor",
            factor_ids=["momentum_3m", "ep_ratio"],
            factor_weights={"momentum_3m": 0.6, "ep_ratio": 0.4},
            selection_rule=SelectionRule.TOP_K,
            selection_params={"k": 10},
            weight_scheme=WeightScheme.EQUAL,
            rebalance_freq=RebalanceFreq.MONTHLY,
            start_date="2020-01-01",
            end_date="2024-12-31",
        )
        result = compiler.compile(config)
        assert result is not None

    def test_compile_empty_factors(self, compiler):
        """Compile with empty factor list raises Pydantic validation error."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            StrategyConfig(
                name="empty",
                factor_ids=[],
                start_date="2020-01-01",
                end_date="2024-12-31",
            )

    def test_compile_nonexistent_factor(self, compiler):
        """Compile with non-existent factor ID raises error."""
        config = StrategyConfig(
            name="bad_factor",
            factor_ids=["nonexistent_factor"],
            start_date="2020-01-01",
            end_date="2024-12-31",
        )
        with pytest.raises(StrategyCompileError):
            compiler.compile(config)

    def test_compile_percentile_selection(self, compiler, sample_factors_in_store):
        """Compile with percentile selection rule."""
        config = StrategyConfig(
            name="percentile_test",
            factor_ids=["momentum_3m"],
            selection_rule=SelectionRule.PERCENTILE,
            selection_params={"percentile": 0.1},
            start_date="2020-01-01",
            end_date="2024-12-31",
        )
        result = compiler.compile(config)
        assert result is not None

    def test_compile_weekly_rebalance(self, compiler, sample_factors_in_store):
        """Compile with weekly rebalance frequency."""
        config = StrategyConfig(
            name="weekly_test",
            factor_ids=["momentum_3m"],
            rebalance_freq=RebalanceFreq.WEEKLY,
            start_date="2020-01-01",
            end_date="2024-12-31",
        )
        result = compiler.compile(config)
        assert result is not None


# ── Fixtures ───────────────────────────────────────────────────────


@pytest.fixture
def compiler(factor_store_with_data):
    """Create a StrategyCompiler with populated factor store."""
    from src.core.strategy_compiler import StrategyCompiler

    return StrategyCompiler(factor_store=factor_store_with_data)


@pytest.fixture
def factor_store_with_data(tmp_path):
    """Create a FactorStore with sample factors loaded."""
    from src.core.factor_store import FactorStore

    store = FactorStore(
        db_path=str(tmp_path / "test.db"),
        chroma_path=str(tmp_path / "chroma"),
    )
    # Load builtin factors
    store.load_builtin_factors()
    return store


@pytest.fixture
def sample_factors_in_store(factor_store_with_data):
    """Ensure sample factors are in the store."""
    return factor_store_with_data
