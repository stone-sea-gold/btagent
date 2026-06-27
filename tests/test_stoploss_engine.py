"""Tests for StopLossEngine — written BEFORE implementation (TDD)."""

import pytest

from src.core.models import StopLossEvent, StopLossRule, StopLossType
from src.core.stoploss_engine import StopLossEngine


class TestStopLossEngine:
    """Test stop-loss rule evaluation."""

    def test_fixed_stop_triggered(self, engine):
        rules = [StopLossRule(rule_type=StopLossType.FIXED, threshold=0.08)]
        events = engine.evaluate_day(
            date="2024-01-15",
            portfolio_value=100000,
            holdings=[{"stock_code": "600519", "cost_price": 100.0, "current_price": 90.0}],
            prices={"600519": 90.0},
            peak_values={"600519": 100.0},
            cost_prices={"600519": 100.0},
            rules=rules,
        )
        assert len(events) == 1
        assert events[0].rule_type == StopLossType.FIXED
        assert events[0].stock_code == "600519"

    def test_fixed_stop_not_triggered(self, engine):
        rules = [StopLossRule(rule_type=StopLossType.FIXED, threshold=0.08)]
        events = engine.evaluate_day(
            date="2024-01-15",
            portfolio_value=100000,
            holdings=[{"stock_code": "600519", "cost_price": 100.0, "current_price": 95.0}],
            prices={"600519": 95.0},
            peak_values={"600519": 100.0},
            cost_prices={"600519": 100.0},
            rules=rules,
        )
        assert len(events) == 0

    def test_trailing_stop_triggered(self, engine):
        rules = [StopLossRule(rule_type=StopLossType.TRAILING, threshold=0.10)]
        events = engine.evaluate_day(
            date="2024-01-15",
            portfolio_value=100000,
            holdings=[{"stock_code": "600519", "current_price": 90.0}],
            prices={"600519": 90.0},
            peak_values={"600519": 100.0},
            cost_prices={"600519": 80.0},
            rules=rules,
        )
        assert len(events) == 1
        assert events[0].rule_type == StopLossType.TRAILING

    def test_trailing_stop_not_triggered(self, engine):
        rules = [StopLossRule(rule_type=StopLossType.TRAILING, threshold=0.10)]
        events = engine.evaluate_day(
            date="2024-01-15",
            portfolio_value=100000,
            holdings=[{"stock_code": "600519", "current_price": 95.0}],
            prices={"600519": 95.0},
            peak_values={"600519": 100.0},
            cost_prices={"600519": 80.0},
            rules=rules,
        )
        assert len(events) == 0

    def test_max_drawdown_triggered(self, engine):
        rules = [StopLossRule(rule_type=StopLossType.MAX_DRAWDOWN, threshold=0.20)]
        events = engine.evaluate_day(
            date="2024-01-15",
            portfolio_value=80000,
            holdings=[],
            prices={},
            peak_values={},
            cost_prices={},
            rules=rules,
            portfolio_peak_value=100000,
        )
        assert len(events) == 1
        assert events[0].rule_type == StopLossType.MAX_DRAWDOWN

    def test_max_drawdown_not_triggered(self, engine):
        rules = [StopLossRule(rule_type=StopLossType.MAX_DRAWDOWN, threshold=0.20)]
        events = engine.evaluate_day(
            date="2024-01-15",
            portfolio_value=85000,
            holdings=[],
            prices={},
            peak_values={},
            cost_prices={},
            rules=rules,
            portfolio_peak_value=100000,
        )
        assert len(events) == 0

    def test_multiple_rules(self, engine):
        rules = [
            StopLossRule(rule_type=StopLossType.FIXED, threshold=0.08),
            StopLossRule(rule_type=StopLossType.TRAILING, threshold=0.10),
        ]
        events = engine.evaluate_day(
            date="2024-01-15",
            portfolio_value=100000,
            holdings=[{"stock_code": "600519", "cost_price": 100.0, "current_price": 90.0}],
            prices={"600519": 90.0},
            peak_values={"600519": 100.0},
            cost_prices={"600519": 100.0},
            rules=rules,
        )
        assert len(events) == 2  # both fixed and trailing triggered

    def test_no_rules_no_events(self, engine):
        events = engine.evaluate_day(
            date="2024-01-15",
            portfolio_value=100000,
            holdings=[{"stock_code": "600519", "cost_price": 100.0, "current_price": 90.0}],
            prices={"600519": 90.0},
            peak_values={"600519": 100.0},
            cost_prices={"600519": 100.0},
            rules=[],
        )
        assert len(events) == 0


@pytest.fixture
def engine():
    return StopLossEngine()
