"""Stop-loss tools for the Agent."""

import json

from src.core.models import StopLossRule, StopLossType
from src.core.stoploss_engine import StopLossEngine
from src.logging import get_logger

logger = get_logger("stoploss_tools")


def add_stoploss_rules(
    strategy_config_json: str,
    rules_json: str,
) -> dict:
    """Add stop-loss rules to a strategy config.

    Args:
        strategy_config_json: JSON strategy config dict.
        rules_json: JSON list of StopLossRule dicts.

    Returns:
        Updated strategy config with stop-loss rules.
    """
    try:
        config = json.loads(strategy_config_json)
        rules_data = json.loads(rules_json)
        rules = [StopLossRule(**r) for r in rules_data]

        config["stoploss_rules"] = [
            {"rule_type": r.rule_type.value, "threshold": r.threshold, "scope": r.scope}
            for r in rules
        ]

        return {
            "strategy_config": config,
            "stoploss_rules_count": len(rules),
            "status": "success",
        }
    except Exception as e:
        logger.error("add_stoploss_rules_error", error=str(e))
        return {"error": str(e), "status": "error"}


def run_backtest_with_stoploss(
    strategy_config_json: str,
    stoploss_rules_json: str,
    compiler=None,
    engine=None,
) -> dict:
    """Run backtest with stop-loss rules applied.

    Args:
        strategy_config_json: JSON strategy config dict.
        stoploss_rules_json: JSON list of StopLossRule dicts.
        compiler: StrategyCompiler instance.
        engine: BacktestEngine instance.

    Returns:
        Backtest result with stop-loss events.
    """
    try:
        config = json.loads(strategy_config_json)
        rules_data = json.loads(stoploss_rules_json)
        rules = [StopLossRule(**r) for r in rules_data]

        # Run standard backtest first
        from src.core.models import StrategyConfig
        from src.tools.backtest_tools import run_backtest

        result = run_backtest(config, compiler, engine)

        if result.get("status") != "success":
            return result

        # Apply stop-loss analysis on the result
        stoploss_engine = StopLossEngine()

        # For now, return the backtest result with stop-loss rules attached
        # Full daily monitoring requires equity_curve data from the backtest
        result["stoploss_rules"] = [
            {"rule_type": r.rule_type.value, "threshold": r.threshold}
            for r in rules
        ]
        result["stoploss_note"] = (
            "止损规则已记录。回测结果基于无止损的原始策略。"
            "止损效果分析需要每日持仓数据，将在后续版本中完善。"
        )

        logger.info("backtest_with_stoploss", rules_count=len(rules))
        return result

    except Exception as e:
        logger.error("run_backtest_with_stoploss_error", error=str(e))
        return {"error": str(e), "status": "error"}


def check_stoploss_scenarios(
    strategy_config_json: str,
    stoploss_rules_json: str,
    compiler=None,
    engine=None,
) -> dict:
    """Analyze what stop-loss events would have triggered.

    Args:
        strategy_config_json: JSON strategy config dict.
        stoploss_rules_json: JSON list of StopLossRule dicts.
        compiler: StrategyCompiler instance.
        engine: BacktestEngine instance.

    Returns:
        Analysis of stop-loss trigger scenarios.
    """
    try:
        rules_data = json.loads(stoploss_rules_json)
        rules = [StopLossRule(**r) for r in rules_data]

        scenarios = []
        for rule in rules:
            if rule.rule_type == StopLossType.FIXED:
                scenarios.append({
                    "rule_type": "固定止损",
                    "threshold": f"{rule.threshold:.0%}",
                    "description": f"当个股从买入价下跌 {rule.threshold:.0%} 时触发卖出",
                })
            elif rule.rule_type == StopLossType.TRAILING:
                scenarios.append({
                    "rule_type": "追踪止损",
                    "threshold": f"{rule.threshold:.0%}",
                    "description": f"当个股从最高点回落 {rule.threshold:.0%} 时触发卖出",
                })
            elif rule.rule_type == StopLossType.MAX_DRAWDOWN:
                scenarios.append({
                    "rule_type": "最大回撤熔断",
                    "threshold": f"{rule.threshold:.0%}",
                    "description": f"当组合整体回撤超过 {rule.threshold:.0%} 时全部清仓",
                })

        return {
            "scenarios": scenarios,
            "total_rules": len(rules),
            "note": "以上为止损规则描述。实际触发分析需要每日价格数据。",
            "status": "success",
        }

    except Exception as e:
        logger.error("check_stoploss_scenarios_error", error=str(e))
        return {"error": str(e), "status": "error"}
