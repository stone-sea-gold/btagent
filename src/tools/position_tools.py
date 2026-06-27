"""Position management tools for the Agent."""

import json

from src.core.models import HoldingRecord, PositionRule, RuleType
from src.core.position_manager import PositionManager
from src.logging import get_logger

logger = get_logger("position_tools")


def save_holdings(
    session_id: str,
    holdings_json: str,
    manager: PositionManager = None,
) -> dict:
    """Save user portfolio holdings.

    Args:
        session_id: Current session ID.
        holdings_json: JSON list of holding dicts.
        manager: PositionManager instance.

    Returns:
        Save result dict.
    """
    try:
        holdings_data = json.loads(holdings_json)
        holdings = [HoldingRecord(**h) for h in holdings_data]
        result = manager.save_holdings(session_id, holdings)
        return result
    except Exception as e:
        logger.error("save_holdings_error", error=str(e))
        return {"error": str(e), "status": "error"}


def get_portfolio_status(
    session_id: str,
    manager: PositionManager = None,
) -> dict:
    """Get portfolio status and check rule violations.

    Args:
        session_id: Current session ID.
        manager: PositionManager instance.

    Returns:
        Portfolio status with violations.
    """
    try:
        holdings = manager.get_holdings(session_id)
        rules = manager.get_rules(session_id)
        violations = manager.check_violations(holdings, rules)

        return {
            "session_id": session_id,
            "holdings_count": len(holdings),
            "holdings": [
                {
                    "stock_code": h.stock_code,
                    "stock_name": h.stock_name,
                    "quantity": h.quantity,
                    "market_value": h.market_value,
                    "weight": h.weight,
                    "pnl_pct": h.pnl_pct,
                }
                for h in holdings
            ],
            "rules_count": len(rules),
            "violations": [
                {
                    "rule_type": v.rule_type.value,
                    "stock_code": v.stock_code,
                    "current_weight": v.current_weight,
                    "max_weight": v.max_weight,
                    "excess": v.excess,
                    "message": v.message,
                }
                for v in violations
            ],
            "violations_count": len(violations),
            "status": "success",
        }
    except Exception as e:
        logger.error("get_portfolio_status_error", error=str(e))
        return {"error": str(e), "status": "error"}


def save_position_rules(
    session_id: str,
    rules_json: str,
    manager: PositionManager = None,
) -> dict:
    """Save position management rules.

    Args:
        session_id: Current session ID.
        rules_json: JSON list of rule dicts.
        manager: PositionManager instance.

    Returns:
        Save result dict.
    """
    try:
        rules_data = json.loads(rules_json)
        rules = [PositionRule(**r) for r in rules_data]
        result = manager.save_rules(session_id, rules)
        return result
    except Exception as e:
        logger.error("save_position_rules_error", error=str(e))
        return {"error": str(e), "status": "error"}
