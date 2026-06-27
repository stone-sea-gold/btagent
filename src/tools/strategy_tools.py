"""Strategy composition tool for the Agent."""

from src.core.models import (
    RebalanceFreq,
    SelectionRule,
    StrategyConfig,
    WeightScheme,
)
from src.logging import get_logger

logger = get_logger("strategy_tools")


def compose_strategy(
    name: str,
    factor_ids: list[str],
    start_date: str,
    end_date: str,
    factor_weights: dict[str, float] | None = None,
    selection_rule: str = "top_k",
    selection_params: dict | None = None,
    weight_scheme: str = "equal",
    rebalance_freq: str = "monthly",
    universe: str = "csi300",
    max_holding: int = 10,
    benchmark: str = "SH000300",
) -> dict:
    """Compose a strategy from factors and parameters.

    Args:
        name: Strategy display name.
        factor_ids: List of factor IDs to use.
        start_date: Backtest start date (YYYY-MM-DD).
        end_date: Backtest end date (YYYY-MM-DD).
        factor_weights: Per-factor weights (default: equal).
        selection_rule: "top_k", "percentile", or "threshold".
        selection_params: Parameters for the selection rule.
        weight_scheme: "equal", "market_cap", or "factor_score".
        rebalance_freq: "daily", "weekly", or "monthly".
        universe: Stock universe ("csi300", "csi500", "all").
        max_holding: Max stocks to hold.
        benchmark: Benchmark index code.

    Returns:
        Strategy config dict.
    """
    try:
        config = StrategyConfig(
            name=name,
            factor_ids=factor_ids,
            factor_weights=factor_weights or {},
            selection_rule=SelectionRule(selection_rule),
            selection_params=selection_params or {"k": max_holding},
            weight_scheme=WeightScheme(weight_scheme),
            rebalance_freq=RebalanceFreq(rebalance_freq),
            universe=universe,
            start_date=start_date,
            end_date=end_date,
            benchmark=benchmark,
            max_holding=max_holding,
        )

        logger.info(
            "compose_strategy",
            name=name,
            factor_count=len(factor_ids),
            selection_rule=selection_rule,
            rebalance_freq=rebalance_freq,
        )

        return {
            "name": config.name,
            "factor_ids": config.factor_ids,
            "factor_weights": config.factor_weights,
            "selection_rule": config.selection_rule.value,
            "selection_params": config.selection_params,
            "weight_scheme": config.weight_scheme.value,
            "rebalance_freq": config.rebalance_freq.value,
            "universe": config.universe,
            "start_date": config.start_date,
            "end_date": config.end_date,
            "benchmark": config.benchmark,
            "max_holding": config.max_holding,
            "status": "composed",
        }
    except Exception as e:
        logger.error("compose_strategy_error", name=name, error=str(e))
        return {"error": str(e), "status": "error"}
