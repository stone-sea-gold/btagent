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

    # ── ATR stop tests ──────────────────────────────────────────

    def test_atr_stop_triggered(self, engine):
        rules = [StopLossRule(rule_type=StopLossType.ATR, threshold=0.0)]
        events = engine.evaluate_day(
            date="2024-01-15",
            portfolio_value=100000,
            holdings=[{"stock_code": "600519", "cost_price": 100.0, "current_price": 93.0}],
            prices={"600519": 93.0},
            peak_values={"600519": 100.0},
            cost_prices={"600519": 100.0},
            rules=rules,
            atr_values={"600519": 5.0},  # stop = 100 - 5*2 = 90, current=93 > 90, not triggered
        )
        assert len(events) == 0

    def test_atr_stop_triggered_below(self, engine):
        rules = [StopLossRule(rule_type=StopLossType.ATR, threshold=0.0, atr_multiplier=2.0)]
        events = engine.evaluate_day(
            date="2024-01-15",
            portfolio_value=100000,
            holdings=[{"stock_code": "600519", "cost_price": 100.0, "current_price": 89.0}],
            prices={"600519": 89.0},
            peak_values={"600519": 100.0},
            cost_prices={"600519": 100.0},
            rules=rules,
            atr_values={"600519": 5.0},  # stop = 100 - 5*2 = 90, current=89 < 90, triggered
        )
        assert len(events) == 1
        assert events[0].rule_type == StopLossType.ATR

    def test_atr_stop_no_atr_data(self, engine):
        rules = [StopLossRule(rule_type=StopLossType.ATR, threshold=0.0)]
        events = engine.evaluate_day(
            date="2024-01-15",
            portfolio_value=100000,
            holdings=[{"stock_code": "600519", "cost_price": 100.0, "current_price": 80.0}],
            prices={"600519": 80.0},
            peak_values={"600519": 100.0},
            cost_prices={"600519": 100.0},
            rules=rules,
            # no atr_values passed — should not trigger
        )
        assert len(events) == 0

    # ── Time stop tests ─────────────────────────────────────────

    def test_time_stop_triggered(self, engine):
        rules = [StopLossRule(rule_type=StopLossType.TIME, threshold=0, max_holding_days=30)]
        events = engine.evaluate_day(
            date="2024-01-15",
            portfolio_value=100000,
            holdings=[{"stock_code": "600519", "current_price": 100.0}],
            prices={"600519": 100.0},
            peak_values={"600519": 100.0},
            cost_prices={"600519": 90.0},
            rules=rules,
            holding_days={"600519": 35},
        )
        assert len(events) == 1
        assert events[0].rule_type == StopLossType.TIME

    def test_time_stop_not_triggered(self, engine):
        rules = [StopLossRule(rule_type=StopLossType.TIME, threshold=0, max_holding_days=30)]
        events = engine.evaluate_day(
            date="2024-01-15",
            portfolio_value=100000,
            holdings=[{"stock_code": "600519", "current_price": 100.0}],
            prices={"600519": 100.0},
            peak_values={"600519": 100.0},
            cost_prices={"600519": 90.0},
            rules=rules,
            holding_days={"600519": 10},
        )
        assert len(events) == 0

    # ── Profit trailing stop tests ──────────────────────────────

    def test_profit_trailing_triggered(self, engine):
        rules = [StopLossRule(
            rule_type=StopLossType.PROFIT_TRAILING, threshold=0,
            profit_trigger_pct=0.1, profit_drawback_pct=0.05,
        )]
        events = engine.evaluate_day(
            date="2024-01-15",
            portfolio_value=100000,
            holdings=[{"stock_code": "600519", "cost_price": 100.0, "current_price": 108.0}],
            prices={"600519": 108.0},
            peak_values={"600519": 115.0},
            cost_prices={"600519": 100.0},
            rules=rules,
            profit_peak_values={"600519": 115.0},  # peak profit = 15%, current = 8%, drawback = 7% > 5%
        )
        assert len(events) == 1
        assert events[0].rule_type == StopLossType.PROFIT_TRAILING

    def test_profit_trailing_not_triggered_below_trigger(self, engine):
        rules = [StopLossRule(
            rule_type=StopLossType.PROFIT_TRAILING, threshold=0,
            profit_trigger_pct=0.1, profit_drawback_pct=0.05,
        )]
        events = engine.evaluate_day(
            date="2024-01-15",
            portfolio_value=100000,
            holdings=[{"stock_code": "600519", "cost_price": 100.0, "current_price": 105.0}],
            prices={"600519": 105.0},
            peak_values={"600519": 105.0},
            cost_prices={"600519": 100.0},
            rules=rules,
            profit_peak_values={"600519": 105.0},  # profit = 5% < 10% trigger, not active
        )
        assert len(events) == 0


@pytest.fixture
def engine():
    return StopLossEngine()
