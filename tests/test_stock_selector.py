"""Tests for StockSelector — written BEFORE implementation (TDD).

Note: These tests require real Qlib data and will be skipped if not available.
"""

import pytest

from src.core.factor_store import FactorStore
from src.core.models import (
    FilterCondition,
    FilterOperator,
    FilterStageConfig,
    ScoreStageConfig,
    StockSelectionConfig,
)
from src.core.stock_selector import StockSelector
from src.exceptions import SelectionFactorError


def _qlib_data_available():
    """Check if Qlib data is available for testing."""
    try:
        from src.data.qlib_setup import check_qlib_data
        info = check_qlib_data()
        return info.get("exists", False)
    except Exception:
        return False


requires_qlib = pytest.mark.skipif(
    not _qlib_data_available(),
    reason="Qlib data not available — run `python cli.py --init-data` first"
)


class TestStockSelectorConfig:
    """Test input validation."""

    def test_valid_config(self):
        config = StockSelectionConfig(
            name="test",
            score_stage=ScoreStageConfig(factor_ids=["momentum_3m"], top_k=10),
            date="2024-01-01",
        )
        assert config.name == "test"
        assert config.score_stage.top_k == 10

    def test_empty_factor_ids_rejected(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            ScoreStageConfig(factor_ids=[], top_k=10)


@requires_qlib
class TestStockSelector:
    """Test stock selection logic."""

    def test_basic_selection(self, selector_with_factors):
        selector, store = selector_with_factors
        config = StockSelectionConfig(
            name="动量选股",
            score_stage=ScoreStageConfig(factor_ids=["momentum_3m"], top_k=5),
            date="2024-01-01",
        )
        result = selector.select(config)
        assert result.config_name == "动量选股"
        assert result.total_selected <= 5
        assert len(result.stocks) <= 5

    def test_selection_with_filter(self, selector_with_factors):
        selector, store = selector_with_factors
        config = StockSelectionConfig(
            name="筛选",
            score_stage=ScoreStageConfig(factor_ids=["momentum_3m"], top_k=10),
            filter_stages=[
                FilterStageConfig(conditions=[
                    FilterCondition(factor_id="momentum_3m", operator=FilterOperator.GT, value=0.0),
                ])
            ],
            date="2024-01-01",
        )
        result = selector.select(config)
        assert result.total_selected <= 10

    def test_multi_factor_weighted(self, selector_with_factors):
        selector, store = selector_with_factors
        config = StockSelectionConfig(
            name="多因子",
            score_stage=ScoreStageConfig(
                factor_ids=["momentum_3m", "ep_ratio"],
                factor_weights={"momentum_3m": 0.6, "ep_ratio": 0.4},
                top_k=10,
            ),
            date="2024-01-01",
        )
        result = selector.select(config)
        assert result.total_selected >= 0

    def test_invalid_factor_id(self, selector_with_factors):
        selector, store = selector_with_factors
        config = StockSelectionConfig(
            name="bad",
            score_stage=ScoreStageConfig(factor_ids=["nonexistent_factor"], top_k=10),
            date="2024-01-01",
        )
        with pytest.raises(SelectionFactorError):
            selector.select(config)

    def test_result_structure(self, selector_with_factors):
        selector, store = selector_with_factors
        config = StockSelectionConfig(
            name="结构",
            score_stage=ScoreStageConfig(factor_ids=["momentum_3m"], top_k=3),
            date="2024-01-01",
        )
        result = selector.select(config)
        assert result.id is not None
        assert result.universe == "csi300"
        assert result.date == "2024-01-01"
        if result.stocks:
            stock = result.stocks[0]
            assert stock.code is not None
            assert isinstance(stock.composite_score, float)


# ── Fixtures ───────────────────────────────────────────────────────


@pytest.fixture
def selector(factor_store):
    return StockSelector(factor_store=factor_store)


@pytest.fixture
def selector_with_factors(factor_store):
    factor_store.load_builtin_factors()
    return StockSelector(factor_store=factor_store), factor_store


@pytest.fixture
def factor_store(tmp_path):
    return FactorStore(db_path=str(tmp_path / "test.db"), chroma_path=str(tmp_path / "chroma"))
