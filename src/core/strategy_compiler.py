"""StrategyCompiler — converts StrategyConfig to Qlib strategy objects.

This is a DETERMINISTIC compiler. No LLM involvement.
Takes a structured StrategyConfig and produces Qlib-compatible strategy objects.

The compiler:
1. Validates all factor IDs exist in the FactorStore
2. Resolves factor formulas
3. Builds a composite alpha expression (weighted sum)
4. Configures selection rule (top-k, percentile, threshold)
5. Returns a compiled strategy dict ready for BacktestEngine
"""

from src.core.factor_store import FactorStore
from src.core.models import (
    Factor,
    SelectionRule,
    StrategyConfig,
    WeightScheme,
)
from src.exceptions import FactorNotFoundError, StrategyCompileError
from src.logging import get_logger

logger = get_logger("strategy_compiler")


class StrategyCompiler:
    """Compiles StrategyConfig into Qlib-executable strategy objects."""

    def __init__(self, factor_store: FactorStore):
        self._factor_store = factor_store

    def compile(self, config: StrategyConfig) -> dict:
        """Compile a strategy config into a Qlib-compatible dict.

        Args:
            config: The strategy configuration.

        Returns:
            Dict with keys: strategy_config, factors, qlib_strategy, alpha_expression.

        Raises:
            StrategyCompileError: If compilation fails.
        """
        if not config.factor_ids:
            raise StrategyCompileError(
                "Cannot compile strategy with empty factor list",
                details={"strategy_name": config.name},
            )

        # Resolve all factors
        factors = []
        for fid in config.factor_ids:
            try:
                factor = self._factor_store.get(fid)
                factors.append(factor)
            except FactorNotFoundError:
                raise StrategyCompileError(
                    f"Factor '{fid}' not found in registry",
                    details={"factor_id": fid, "strategy_name": config.name},
                )

        # Build composite alpha expression
        alpha_expr = self._build_alpha_expression(config, factors)

        # Build selection expression
        selection_expr = self._build_selection_expression(config)

        # Build weight expression
        weight_expr = self._build_weight_expression(config, factors)

        # Determine rebalance days
        rebalance_days = self._get_rebalance_days(config.rebalance_freq)

        compiled = {
            "strategy_config": config,
            "factors": [{"id": f.id, "formula": f.formula, "name": f.name} for f in factors],
            "alpha_expression": alpha_expr,
            "selection_expression": selection_expr,
            "weight_expression": weight_expr,
            "rebalance_days": rebalance_days,
            "qlib_strategy": self._build_qlib_strategy_dict(
                config, alpha_expr, selection_expr, weight_expr, rebalance_days
            ),
        }

        logger.info(
            "strategy_compiled",
            strategy_name=config.name,
            factor_count=len(factors),
            selection_rule=config.selection_rule.value,
            rebalance_freq=config.rebalance_freq.value,
        )
        return compiled

    def _build_alpha_expression(self, config: StrategyConfig, factors: list[Factor]) -> str:
        """Build a composite alpha expression from factors.

        If multiple factors, creates a weighted sum.
        If single factor, uses the raw expression.
        """
        if len(factors) == 1:
            return factors[0].formula

        terms = []
        for factor in factors:
            weight = config.factor_weights.get(factor.id, 1.0 / len(factors))
            terms.append(f"({weight}) * ({factor.formula})")

        return " + ".join(terms)

    def _build_selection_expression(self, config: StrategyConfig) -> dict:
        """Build the stock selection expression based on the rule."""
        if config.selection_rule == SelectionRule.TOP_K:
            k = config.selection_params.get("k", config.max_holding)
            return {"method": "top_k", "k": k}

        elif config.selection_rule == SelectionRule.PERCENTILE:
            percentile = config.selection_params.get("percentile", 0.1)
            return {"method": "percentile", "percentile": percentile}

        elif config.selection_rule == SelectionRule.THRESHOLD:
            threshold = config.selection_params.get("threshold", 0)
            return {"method": "threshold", "threshold": threshold}

        else:
            raise StrategyCompileError(
                f"Unknown selection rule: {config.selection_rule}",
                details={"selection_rule": config.selection_rule.value},
            )

    def _build_weight_expression(self, config: StrategyConfig, factors: list[Factor]) -> dict:
        """Build the weight allocation expression."""
        if config.weight_scheme == WeightScheme.EQUAL:
            return {"method": "equal"}

        elif config.weight_scheme == WeightScheme.FACTOR_SCORE:
            return {"method": "factor_score"}

        elif config.weight_scheme == WeightScheme.MARKET_CAP:
            return {"method": "market_cap"}

        else:
            raise StrategyCompileError(
                f"Unknown weight scheme: {config.weight_scheme}",
                details={"weight_scheme": config.weight_scheme.value},
            )

    def _get_rebalance_days(self, freq) -> int:
        """Convert rebalance frequency to trading days."""
        mapping = {
            "daily": 1,
            "weekly": 5,
            "monthly": 20,
        }
        return mapping.get(freq.value, 20)

    def _build_qlib_strategy_dict(
        self, config, alpha_expr, selection_expr, weight_expr, rebalance_days
    ) -> dict:
        """Build the final Qlib strategy configuration dict."""
        return {
            "class": "TopkDropoutStrategy",
            "module_path": "qlib.contrib.strategy",
            "kwargs": {
                "signal": alpha_expr,
                "topk": selection_expr.get("k", config.max_holding),
                "n_drop": selection_expr.get("k", config.max_holding) // 5,
                "method_sell": "bottom",
                "method_buy": "top",
                "rebalance_days": rebalance_days,
            },
        }
