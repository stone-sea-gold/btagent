"""Tests for BacktestEngine — written BEFORE implementation (TDD).

Tests cover:
- Run backtest with valid strategy
- Parse results (metrics, equity curve)
- Idempotency (same inputs return cached result)
- Error handling (invalid dates, empty strategy)
"""

import pytest

from src.core.backtest_engine import BacktestEngine
from src.core.models import (
    BacktestMetrics,
    RebalanceFreq,
    SelectionRule,
    StrategyConfig,
    WeightScheme,
)


class TestBacktestEngine:
    """Test backtest execution and result parsing."""

    def test_run_basic_backtest(self, engine, compiled_strategy):
        """Run a basic backtest and check result structure."""
        result = engine.run(
            strategy_id="test_001",
            compiled_strategy=compiled_strategy,
            start_date="2023-01-01",
            end_date="2023-12-31",
        )
        assert result is not None
        assert result.strategy_id == "test_001"
        assert result.metrics is not None
        assert isinstance(result.metrics, BacktestMetrics)

    def test_result_metrics_range(self, engine, compiled_strategy):
        """Check that backtest metrics are within reasonable ranges."""
        result = engine.run(
            strategy_id="test_002",
            compiled_strategy=compiled_strategy,
            start_date="2023-01-01",
            end_date="2023-12-31",
        )
        m = result.metrics
        # Sharpe ratio should be finite
        assert -10 < m.sharpe_ratio < 10
        # Max drawdown should be negative or zero
        assert m.max_drawdown <= 0
        # Win rate should be between 0 and 1
        assert 0 <= m.win_rate <= 1
        # Volatility should be positive
        assert m.volatility >= 0

    def test_idempotency(self, engine, compiled_strategy):
        """Same inputs should return cached result."""
        result1 = engine.run(
            strategy_id="test_003",
            compiled_strategy=compiled_strategy,
            start_date="2023-01-01",
            end_date="2023-12-31",
        )
        result2 = engine.run(
            strategy_id="test_003",
            compiled_strategy=compiled_strategy,
            start_date="2023-01-01",
            end_date="2023-12-31",
        )
        assert result2.is_cached is True
        assert result1.metrics.sharpe_ratio == result2.metrics.sharpe_ratio

    def test_different_dates_not_cached(self, engine, compiled_strategy):
        """Different date ranges should not return cached results."""
        result1 = engine.run(
            strategy_id="test_004",
            compiled_strategy=compiled_strategy,
            start_date="2023-01-01",
            end_date="2023-06-30",
        )
        result2 = engine.run(
            strategy_id="test_004",
            compiled_strategy=compiled_strategy,
            start_date="2023-07-01",
            end_date="2023-12-31",
        )
        assert result2.is_cached is False

    def test_equity_curve_not_empty(self, engine, compiled_strategy):
        """Equity curve should have data points."""
        result = engine.run(
            strategy_id="test_005",
            compiled_strategy=compiled_strategy,
            start_date="2023-01-01",
            end_date="2023-12-31",
        )
        assert len(result.equity_curve) > 0


# ── Fixtures ───────────────────────────────────────────────────────


@pytest.fixture
def engine(tmp_path):
    """Create a BacktestEngine with temporary storage."""
    from src.core.backtest_engine import BacktestEngine

    return BacktestEngine(cache_dir=str(tmp_path / "backtest_cache"))


@pytest.fixture
def compiled_strategy():
    """A mock compiled strategy for testing."""
    return {
        "strategy_config": StrategyConfig(
            name="test_strategy",
            factor_ids=["momentum_3m"],
            selection_rule=SelectionRule.TOP_K,
            selection_params={"k": 10},
            weight_scheme=WeightScheme.EQUAL,
            rebalance_freq=RebalanceFreq.MONTHLY,
            start_date="2023-01-01",
            end_date="2023-12-31",
        ),
        "qlib_strategy": None,  # Will be set by compiler
        "factors": [{"id": "momentum_3m", "formula": "Ref($close, 0) / Ref($close, 60) - 1"}],
    }
