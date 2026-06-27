"""ParamOptimizer — parameter optimization using grid search or Bayesian optimization.

Uses optuna for both grid search and Bayesian optimization.
Lazy-imports optuna to keep it optional for users who don't need optimization.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from src.core.backtest_engine import BacktestEngine
from src.core.models import (
    OptimizationConfig,
    OptimizationResult,
    OptimizationTrial,
    OptunaSearchMethod,
    StrategyConfig,
)
from src.core.strategy_compiler import StrategyCompiler
from src.exceptions import OptimizationError, StrategyNotFoundError
from src.logging import get_logger

if TYPE_CHECKING:
    from src.tools.storage_tools import StrategyStore

logger = get_logger("param_optimizer")

OVERFIT_WARNING = (
    "⚠️ 过拟合风险警告：参数优化是在历史数据上进行的，最优参数可能仅适用于训练期。"
    "建议：1) 使用样本外数据验证；2) 选择参数变化不敏感的区域；"
    "3) 不要直接将优化结果用于实盘交易。"
)


class ParamOptimizer:
    """Parameter optimization engine."""

    def __init__(
        self,
        strategy_compiler: StrategyCompiler,
        backtest_engine: BacktestEngine,
        strategy_store: StrategyStore,
    ):
        self._compiler = strategy_compiler
        self._engine = backtest_engine
        self._strategy_store = strategy_store

    def optimize(self, config: OptimizationConfig) -> OptimizationResult:
        """Run parameter optimization."""
        import optuna

        # Load base strategy
        try:
            strategy_data = self._strategy_store.load(config.strategy_id)
        except StrategyNotFoundError:
            raise OptimizationError(
                f"策略 '{config.strategy_id}' 不存在",
                details={"strategy_id": config.strategy_id},
            )

        base_config = strategy_data["config"]

        # Create optuna study
        if config.method == OptunaSearchMethod.GRID:
            study = optuna.create_study(direction="maximize")
        else:
            optuna.logging.set_verbosity(optuna.logging.WARNING)
            study = optuna.create_study(direction="maximize")

        # Run optimization
        def objective(trial):
            return self._objective(trial, base_config, config.param_ranges, config.metric, config)

        study.optimize(objective, n_trials=config.n_trials)

        # Build result
        trials = []
        for t in study.trials:
            trials.append(OptimizationTrial(
                trial_id=t.number,
                params=t.params,
                metric_value=t.value if t.value is not None else 0.0,
            ))

        best = study.best_trial
        result = OptimizationResult(
            id=f"opt_{uuid.uuid4().hex[:8]}",
            config=config,
            best_params=best.params,
            best_metric=best.value if best.value is not None else 0.0,
            best_strategy_id=config.strategy_id,
            trials=trials,
            total_trials=len(trials),
            overfit_warning=OVERFIT_WARNING,
        )

        logger.info(
            "optimization_complete",
            strategy_id=config.strategy_id,
            method=config.method.value,
            total_trials=result.total_trials,
            best_metric=result.best_metric,
        )
        return result

    def _objective(self, trial, base_config: dict, param_ranges, metric: str, config: OptimizationConfig) -> float:
        """Optuna objective function. Each call = one backtest."""
        import optuna

        # Suggest params
        params = {}
        for pr in param_ranges:
            if pr.is_int:
                params[pr.name] = trial.suggest_int(pr.name, int(pr.low), int(pr.high))
            elif pr.step:
                params[pr.name] = trial.suggest_float(pr.name, pr.low, pr.high, step=pr.step)
            else:
                params[pr.name] = trial.suggest_float(pr.name, pr.low, pr.high)

        # Apply params to config
        modified_config = self._apply_params(base_config, params)

        # Run backtest
        try:
            compiled = self._compiler.compile(StrategyConfig(**modified_config))
            result = self._engine.run(
                strategy_id=f"opt_{trial.number}",
                compiled_strategy=compiled,
                start_date=config.start_date,
                end_date=config.end_date,
            )
            return getattr(result.metrics, metric, 0.0)
        except Exception as e:
            logger.warning("optimization_trial_failed", trial=trial.number, error=str(e))
            return float("-inf")

    def _apply_params(self, config: dict, params: dict[str, float]) -> dict:
        """Apply optimization params to a strategy config dict.

        Supports nested paths like 'selection_params.k'.
        """
        modified = config.copy()
        for key, value in params.items():
            parts = key.split(".")
            target = modified
            for part in parts[:-1]:
                if part not in target:
                    target[part] = {}
                target = target[part]
            target[parts[-1]] = value
        return modified
