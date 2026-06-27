"""Tests for ParamOptimizer — written BEFORE implementation (TDD)."""

import pytest

from src.core.models import OptunaSearchMethod, OptimizationConfig, ParamRange
from src.core.param_optimizer import ParamOptimizer
from src.exceptions import OptimizationError


class TestParamOptimizerConfig:
    """Test input validation."""

    def test_valid_config(self):
        config = OptimizationConfig(
            strategy_id="strat_001",
            method=OptunaSearchMethod.GRID,
            param_ranges=[ParamRange(name="max_holding", low=5, high=20, step=5, is_int=True)],
            start_date="2020-01-01",
            end_date="2024-12-31",
        )
        assert config.strategy_id == "strat_001"
        assert config.n_trials == 50

    def test_empty_param_ranges_rejected(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            OptimizationConfig(
                strategy_id="strat_001",
                method=OptunaSearchMethod.GRID,
                param_ranges=[],
                start_date="2020-01-01",
                end_date="2024-12-31",
            )


class TestParamOptimizer:
    """Test parameter optimization."""

    def test_grid_search(self, optimizer_with_strategy):
        optimizer, strategy_id = optimizer_with_strategy
        config = OptimizationConfig(
            strategy_id=strategy_id,
            method=OptunaSearchMethod.GRID,
            param_ranges=[
                ParamRange(name="max_holding", low=5, high=15, step=5, is_int=True),
            ],
            n_trials=5,
            start_date="2023-01-01",
            end_date="2023-12-31",
        )
        result = optimizer.optimize(config)
        assert result.total_trials > 0
        assert result.best_metric is not None
        assert result.overfit_warning != ""

    def test_bayesian_search(self, optimizer_with_strategy):
        optimizer, strategy_id = optimizer_with_strategy
        config = OptimizationConfig(
            strategy_id=strategy_id,
            method=OptunaSearchMethod.BAYESIAN,
            param_ranges=[
                ParamRange(name="max_holding", low=5, high=20, is_int=True),
            ],
            n_trials=5,
            start_date="2023-01-01",
            end_date="2023-12-31",
        )
        result = optimizer.optimize(config)
        assert result.total_trials > 0

    def test_result_structure(self, optimizer_with_strategy):
        optimizer, strategy_id = optimizer_with_strategy
        config = OptimizationConfig(
            strategy_id=strategy_id,
            method=OptunaSearchMethod.GRID,
            param_ranges=[
                ParamRange(name="max_holding", low=5, high=10, step=5, is_int=True),
            ],
            n_trials=5,
            start_date="2023-01-01",
            end_date="2023-12-31",
        )
        result = optimizer.optimize(config)
        assert result.id is not None
        assert result.best_strategy_id is not None
        assert len(result.trials) > 0

    def test_overfit_warning_present(self, optimizer_with_strategy):
        optimizer, strategy_id = optimizer_with_strategy
        config = OptimizationConfig(
            strategy_id=strategy_id,
            method=OptunaSearchMethod.GRID,
            param_ranges=[
                ParamRange(name="max_holding", low=5, high=10, step=5, is_int=True),
            ],
            n_trials=5,
            start_date="2023-01-01",
            end_date="2023-12-31",
        )
        result = optimizer.optimize(config)
        assert "过拟合" in result.overfit_warning or "overfit" in result.overfit_warning.lower()

    def test_invalid_strategy_id(self, optimizer):
        config = OptimizationConfig(
            strategy_id="nonexistent",
            method=OptunaSearchMethod.GRID,
            param_ranges=[
                ParamRange(name="max_holding", low=5, high=10, step=5, is_int=True),
            ],
            n_trials=5,
            start_date="2023-01-01",
            end_date="2023-12-31",
        )
        with pytest.raises(OptimizationError):
            optimizer.optimize(config)


# ── Fixtures ───────────────────────────────────────────────────────


@pytest.fixture
def optimizer(tmp_path):
    from src.core.backtest_engine import BacktestEngine
    from src.core.factor_store import FactorStore
    from src.core.strategy_compiler import StrategyCompiler
    from src.tools.storage_tools import StrategyStore

    factor_store = FactorStore(db_path=str(tmp_path / "factors.db"), chroma_path=str(tmp_path / "chroma"))
    factor_store.load_builtin_factors()
    compiler = StrategyCompiler(factor_store=factor_store)
    engine = BacktestEngine(cache_dir=str(tmp_path / "cache"))
    store = StrategyStore(db_path=str(tmp_path / "strategies.db"), chroma_path=str(tmp_path / "chroma2"))
    return ParamOptimizer(strategy_compiler=compiler, backtest_engine=engine, strategy_store=store)


@pytest.fixture
def optimizer_with_strategy(optimizer):
    from src.tools.storage_tools import save_strategy

    config = {
        "name": "测试策略",
        "factor_ids": ["momentum_3m"],
        "start_date": "2023-01-01",
        "end_date": "2023-12-31",
        "selection_rule": "top_k",
        "selection_params": {"k": 10},
        "weight_scheme": "equal",
        "rebalance_freq": "monthly",
        "universe": "csi300",
        "max_holding": 10,
    }
    result = save_strategy("测试策略", config, optimizer._strategy_store)
    return optimizer, result["strategy_id"]
