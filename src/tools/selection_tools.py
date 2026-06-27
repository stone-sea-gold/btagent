"""Stock selection tools for the Agent."""

import json

from src.core.models import (
    FilterStageConfig,
    ScoreStageConfig,
    StockSelectionConfig,
)
from src.core.stock_selector import StockSelector
from src.logging import get_logger

logger = get_logger("selection_tools")


def select_stocks(
    name: str,
    factor_ids: str,
    top_k: int = 50,
    factor_weights_json: str = "",
    filter_conditions_json: str = "",
    universe: str = "csi300",
    date: str = "",
    selector: StockSelector = None,
) -> dict:
    """Run stock selection pipeline.

    Args:
        name: Selection name.
        factor_ids: Comma-separated factor IDs.
        top_k: Number of top stocks to select.
        factor_weights_json: JSON dict of factor weights (optional).
        filter_conditions_json: JSON list of filter conditions (optional).
        universe: Stock universe (csi300, csi500, all).
        date: Evaluation date (YYYY-MM-DD).
        selector: StockSelector instance.

    Returns:
        Selection result dict.
    """
    try:
        fid_list = [f.strip() for f in factor_ids.split(",") if f.strip()]
        weights = json.loads(factor_weights_json) if factor_weights_json else {}

        filter_stages = []
        if filter_conditions_json:
            conditions_data = json.loads(filter_conditions_json)
            filter_stages = [FilterStageConfig(conditions=conditions_data)]

        config = StockSelectionConfig(
            name=name,
            universe=universe,
            score_stage=ScoreStageConfig(
                factor_ids=fid_list,
                factor_weights=weights,
                top_k=top_k,
            ),
            filter_stages=filter_stages,
            date=date,
        )

        result = selector.select(config)

        return {
            "selection_id": result.id,
            "name": result.config_name,
            "universe": result.universe,
            "date": result.date,
            "total_scored": result.total_scored,
            "total_selected": result.total_selected,
            "stocks": [
                {
                    "code": s.code,
                    "name": s.name,
                    "composite_score": s.composite_score,
                    "factor_scores": s.factor_scores,
                }
                for s in result.stocks
            ],
            "status": "success",
        }
    except Exception as e:
        logger.error("select_stocks_error", error=str(e))
        return {"error": str(e), "status": "error"}
