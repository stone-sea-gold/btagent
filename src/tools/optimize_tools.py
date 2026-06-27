"""Parameter optimization tools for the Agent."""

import json

from src.core.models import (
    OptunaSearchMethod,
    OptimizationConfig,
    ParamRange,
)
from src.core.param_optimizer import ParamOptimizer
from src.logging import get_logger

logger = get_logger("optimize_tools")


def optimize_parameters(
    strategy_id: str,
    method: str = "bayesian",
    param_ranges_json: str = "",
    metric: str = "sharpe_ratio",
    n_trials: int = 50,
    start_date: str = "",
    end_date: str = "",
    optimizer: ParamOptimizer = None,
) -> dict:
    """Run parameter optimization on a strategy.

    Args:
        strategy_id: ID of the strategy to optimize.
        method: "grid" or "bayesian".
        param_ranges_json: JSON list of ParamRange dicts.
        metric: Metric to maximize (default: sharpe_ratio).
        n_trials: Number of optimization trials.
        start_date: Backtest start date.
        end_date: Backtest end date.
        optimizer: ParamOptimizer instance.

    Returns:
        Optimization result dict with overfitting warning.
    """
    try:
        ranges_data = json.loads(param_ranges_json) if param_ranges_json else []
        param_ranges = [ParamRange(**r) for r in ranges_data]

        config = OptimizationConfig(
            strategy_id=strategy_id,
            method=OptunaSearchMethod(method),
            param_ranges=param_ranges,
            metric=metric,
            n_trials=n_trials,
            start_date=start_date,
            end_date=end_date,
        )

        result = optimizer.optimize(config)

        return {
            "optimization_id": result.id,
            "strategy_id": result.best_strategy_id,
            "best_params": result.best_params,
            "best_metric": result.best_metric,
            "metric": metric,
            "total_trials": result.total_trials,
            "trials": [
                {"trial_id": t.trial_id, "params": t.params, "metric_value": t.metric_value}
                for t in result.trials
            ],
            "overfit_warning": result.overfit_warning,
            "status": "success",
        }
    except Exception as e:
        logger.error("optimize_parameters_error", error=str(e))
        return {"error": str(e), "status": "error"}
