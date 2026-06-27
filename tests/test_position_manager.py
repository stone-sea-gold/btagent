"""Tests for PositionManager — written BEFORE implementation (TDD)."""

import pytest

from src.core.models import HoldingRecord, PositionRule, RuleType
from src.core.position_manager import PositionManager


class TestPositionManager:
    """Test PositionManager CRUD and violation checking."""

    def test_save_and_get_holdings(self, manager):
        holdings = [
            HoldingRecord(stock_code="600519", stock_name="茅台", quantity=100,
                          cost_price=1800.0, current_price=1900.0, market_value=190000.0,
                          weight=0.3),
        ]
        manager.save_holdings("s1", holdings)
        result = manager.get_holdings("s1")
        assert len(result) == 1
        assert result[0].stock_code == "600519"

    def test_update_existing_holding(self, manager):
        h1 = HoldingRecord(stock_code="600519", quantity=100,
                           cost_price=1800.0, current_price=1900.0, market_value=190000.0)
        manager.save_holdings("s1", [h1])
        h2 = HoldingRecord(stock_code="600519", quantity=200,
                           cost_price=1800.0, current_price=1950.0, market_value=390000.0)
        manager.save_holdings("s1", [h2])
        result = manager.get_holdings("s1")
        assert len(result) == 1
        assert result[0].quantity == 200

    def test_save_and_get_rules(self, manager):
        rules = [
            PositionRule(rule_type=RuleType.SINGLE_STOCK_LIMIT, max_weight=0.2),
            PositionRule(rule_type=RuleType.TOTAL_POSITION_LIMIT, max_weight=0.8),
        ]
        manager.save_rules("s1", rules)
        result = manager.get_rules("s1")
        assert len(result) == 2

    def test_check_single_stock_violation(self, manager):
        holdings = [
            HoldingRecord(stock_code="600519", quantity=100,
                          cost_price=1800.0, current_price=1900.0,
                          market_value=190000.0, weight=0.25),
        ]
        rules = [PositionRule(rule_type=RuleType.SINGLE_STOCK_LIMIT, max_weight=0.2)]
        violations = manager.check_violations(holdings, rules)
        assert len(violations) == 1
        assert violations[0].stock_code == "600519"

    def test_check_total_position_violation(self, manager):
        holdings = [
            HoldingRecord(stock_code="600519", quantity=100,
                          cost_price=1800.0, current_price=1900.0,
                          market_value=190000.0, weight=0.5),
            HoldingRecord(stock_code="000858", quantity=200,
                          cost_price=150.0, current_price=160.0,
                          market_value=32000.0, weight=0.4),
        ]
        rules = [PositionRule(rule_type=RuleType.TOTAL_POSITION_LIMIT, max_weight=0.8)]
        violations = manager.check_violations(holdings, rules)
        assert len(violations) == 1
        assert "总仓位" in violations[0].message

    def test_no_violations(self, manager):
        holdings = [
            HoldingRecord(stock_code="600519", quantity=100,
                          cost_price=1800.0, current_price=1900.0,
                          market_value=190000.0, weight=0.1),
        ]
        rules = [PositionRule(rule_type=RuleType.SINGLE_STOCK_LIMIT, max_weight=0.2)]
        violations = manager.check_violations(holdings, rules)
        assert len(violations) == 0

    def test_empty_holdings(self, manager):
        rules = [PositionRule(rule_type=RuleType.SINGLE_STOCK_LIMIT, max_weight=0.2)]
        violations = manager.check_violations([], rules)
        assert len(violations) == 0

    def test_multiple_rules(self, manager):
        holdings = [
            HoldingRecord(stock_code="600519", quantity=100,
                          cost_price=1800.0, current_price=1900.0,
                          market_value=190000.0, weight=0.25),
        ]
        rules = [
            PositionRule(rule_type=RuleType.SINGLE_STOCK_LIMIT, max_weight=0.2),
            PositionRule(rule_type=RuleType.TOTAL_POSITION_LIMIT, max_weight=0.9),
        ]
        violations = manager.check_violations(holdings, rules)
        assert len(violations) == 1  # only single stock violated


@pytest.fixture
def manager(tmp_path):
    return PositionManager(db_path=str(tmp_path / "positions.db"))
