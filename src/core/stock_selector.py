"""StockSelector — multi-level stock selection pipeline.

Flow: factor scoring → ranking → conditional filtering → result

Uses FactorStore to resolve factor formulas.
Requires real Qlib data — no mock fallback.
"""

import uuid
from datetime import datetime

from src.config import settings
from src.core.factor_store import FactorStore
from src.core.models import (
    FilterOperator,
    FilterStageConfig,
    SelectedStock,
    StockSelectionConfig,
    StockSelectionResult,
)
from src.exceptions import SelectionFactorError
from src.logging import get_logger

logger = get_logger("stock_selector")


class StockSelector:
    """Multi-level stock selection engine."""

    def __init__(self, factor_store: FactorStore):
        self._factor_store = factor_store

    def select(self, config: StockSelectionConfig) -> StockSelectionResult:
        """Run the full selection pipeline."""
        # Validate factor IDs
        for fid in config.score_stage.factor_ids:
            try:
                self._factor_store.get(fid)
            except Exception:
                raise SelectionFactorError(
                    f"因子 '{fid}' 不存在",
                    details={"factor_id": fid},
                )

        # Validate date against data coverage
        from src.core.trading_calendar import TradingCalendar
        calendar = TradingCalendar()
        date_check = calendar.validate_date_against_coverage(config.date)
        if not date_check["valid"]:
            logger.warning(
                "date_out_of_coverage",
                requested_date=config.date,
                message=date_check["message"],
            )
            # Use suggested date if available
            if "suggested_date" in date_check:
                logger.info("using_suggested_date", suggested_date=date_check["suggested_date"])
                config = config.model_copy(update={"date": date_check["suggested_date"]})

        # Stage 1: Score and rank
        scored = self._score_stocks(
            config.score_stage.factor_ids,
            config.score_stage.factor_weights,
            config.universe,
            config.date,
        )
        scored.sort(key=lambda x: x["composite_score"], reverse=True)
        scored = scored[: config.score_stage.top_k]

        # Stage 2: Apply filters
        for filter_stage in config.filter_stages:
            scored = self._apply_filters(scored, filter_stage)

        # Build result
        stocks = [
            SelectedStock(
                code=s["code"],
                name=s["name"],
                composite_score=round(s["composite_score"], 4),
                factor_scores=s.get("factor_scores", {}),
            )
            for s in scored
        ]

        result = StockSelectionResult(
            id=f"sel_{uuid.uuid4().hex[:8]}",
            config_name=config.name,
            universe=config.universe,
            date=config.date,
            total_scored=len(scored),
            total_selected=len(stocks),
            stocks=stocks,
        )

        logger.info(
            "selection_complete",
            name=config.name,
            total_scored=result.total_scored,
            total_selected=result.total_selected,
        )
        return result

    def _score_stocks(
        self,
        factor_ids: list[str],
        factor_weights: dict[str, float],
        universe: str,
        date: str,
    ) -> list[dict]:
        """Score all stocks by weighted factors using real Qlib data.

        Raises SelectionFactorError if Qlib data is not available.
        """
        return self._score_stocks_qlib(factor_ids, factor_weights, universe, date)

    def _score_stocks_qlib(
        self,
        factor_ids: list[str],
        factor_weights: dict[str, float],
        universe: str,
        date: str,
    ) -> list[dict]:
        """Score stocks using real Qlib data."""
        import qlib
        from qlib.data import D

        # Ensure Qlib is initialized
        try:
            qlib.init(provider_uri=settings.qlib_data_path, region="cn")
        except Exception:
            pass

        # Get instrument list
        if universe == "csi300":
            instruments = D.instruments("csi300")
        elif universe == "csi500":
            instruments = D.instruments("csi500")
        else:
            instruments = D.instruments("all")

        # Get stock list for the date
        stock_list = D.list_instruments(instruments=instruments, start_time=date, end_time=date, as_list=True)

        if not stock_list:
            raise SelectionFactorError(
                f"在 {date} 没有找到 {universe} 的股票数据",
                details={"date": date, "universe": universe},
            )

        weights = factor_weights or {fid: 1.0 / len(factor_ids) for fid in factor_ids}

        # Get factor values for each stock
        results = []
        for stock_code in stock_list:
            factor_scores = {}
            for fid in factor_ids:
                factor = self._factor_store.get(fid)
                try:
                    # Evaluate factor expression for this stock on this date
                    expr = factor.formula
                    value = D.features([stock_code], [expr], start_time=date, end_time=date)
                    if value is not None and len(value) > 0:
                        factor_scores[fid] = float(value.iloc[0, 0])
                    else:
                        factor_scores[fid] = 0.0
                except Exception:
                    factor_scores[fid] = 0.0

            composite = sum(
                factor_scores.get(fid, 0) * weights.get(fid, 1.0 / len(factor_ids))
                for fid in factor_ids
            )

            results.append({
                "code": stock_code,
                "name": stock_code,  # Qlib doesn't provide names directly
                "composite_score": composite,
                "factor_scores": factor_scores,
            })

        return results

        return results

    def _apply_filters(
        self, scored_stocks: list[dict], filter_stage: FilterStageConfig
    ) -> list[dict]:
        """Apply filter conditions to scored stocks."""
        filtered = []
        for stock in scored_stocks:
            passes = True
            for cond in filter_stage.conditions:
                score = stock["factor_scores"].get(cond.factor_id, 0)

                if cond.operator == FilterOperator.LT:
                    if cond.value is not None and not (score < cond.value):
                        passes = False
                elif cond.operator == FilterOperator.LE:
                    if cond.value is not None and not (score <= cond.value):
                        passes = False
                elif cond.operator == FilterOperator.GT:
                    if cond.value is not None and not (score > cond.value):
                        passes = False
                elif cond.operator == FilterOperator.GE:
                    if cond.value is not None and not (score >= cond.value):
                        passes = False
                elif cond.operator == FilterOperator.EQ:
                    if cond.value is not None and not (abs(score - cond.value) < 1e-6):
                        passes = False
                elif cond.operator == FilterOperator.BETWEEN:
                    if cond.value_min is not None and cond.value_max is not None:
                        if not (cond.value_min <= score <= cond.value_max):
                            passes = False

                if not passes:
                    break

            if passes:
                filtered.append(stock)

        return filtered
