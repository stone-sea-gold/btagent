"""Backtest tools for the Agent."""

from src.core.backtest_engine import BacktestEngine
from src.core.models import StrategyConfig
from src.core.strategy_compiler import StrategyCompiler
from src.logging import get_logger

logger = get_logger("backtest_tools")


def run_backtest(
    strategy_config: dict,
    compiler: StrategyCompiler,
    engine: BacktestEngine,
) -> dict:
    """Compile and run a backtest for the given strategy config.

    Args:
        strategy_config: Strategy config dict (from compose_strategy).
        compiler: StrategyCompiler instance.
        engine: BacktestEngine instance.

    Returns:
        Backtest result dict with metrics.
    """
    try:
        config = StrategyConfig(**strategy_config)
        compiled = compiler.compile(config)
        result = engine.run(
            strategy_id=config.name,
            compiled_strategy=compiled,
            start_date=config.start_date,
            end_date=config.end_date,
            benchmark=config.benchmark,
        )

        logger.info(
            "run_backtest_complete",
            strategy_name=config.name,
            sharpe=result.metrics.sharpe_ratio,
            total_return=result.metrics.total_return,
        )

        return {
            "backtest_id": result.id,
            "strategy_name": config.name,
            "metrics": {
                "total_return": result.metrics.total_return,
                "annualized_return": result.metrics.annualized_return,
                "sharpe_ratio": result.metrics.sharpe_ratio,
                "max_drawdown": result.metrics.max_drawdown,
                "volatility": result.metrics.volatility,
                "win_rate": result.metrics.win_rate,
                "turnover": result.metrics.turnover,
            },
            "equity_curve_summary": {
                "data_points": len(result.equity_curve),
                "start_value": result.equity_curve[0]["value"] if result.equity_curve else 1.0,
                "end_value": result.equity_curve[-1]["value"] if result.equity_curve else 1.0,
            },
            "is_cached": result.is_cached,
            "status": "success",
        }
    except Exception as e:
        logger.error("run_backtest_error", error=str(e))
        return {"error": str(e), "status": "error"}


def analyze_backtest(backtest_result: dict) -> str:
    """Generate natural language analysis of backtest results.

    Args:
        backtest_result: Result dict from run_backtest.

    Returns:
        Natural language analysis string.
    """
    if backtest_result.get("status") != "success":
        return f"回测未能成功完成：{backtest_result.get('error', '未知错误')}"

    m = backtest_result.get("metrics", {})
    name = backtest_result.get("strategy_name", "策略")

    lines = [f"## {name} 回测分析\n"]

    # Overall assessment
    sharpe = m.get("sharpe_ratio", 0)
    if sharpe > 1.5:
        lines.append("**表现优秀** — 夏普比率 > 1.5，风险调整后收益显著。")
    elif sharpe > 0.5:
        lines.append("**表现良好** — 夏普比率 > 0.5，具有一定的超额收益能力。")
    elif sharpe > 0:
        lines.append("**表现一般** — 夏普比率接近 0，收益与风险基本匹配。")
    else:
        lines.append("**表现不佳** — 夏普比率为负，策略可能存在问题。")

    lines.append("")

    # Key metrics
    lines.append("### 关键指标")
    lines.append(f"- 总收益率: {m.get('total_return', 0):.2%}")
    lines.append(f"- 年化收益率: {m.get('annualized_return', 0):.2%}")
    lines.append(f"- 夏普比率: {sharpe:.2f}")
    lines.append(f"- 最大回撤: {m.get('max_drawdown', 0):.2%}")
    lines.append(f"- 年化波动率: {m.get('volatility', 0):.2%}")
    lines.append(f"- 胜率: {m.get('win_rate', 0):.2%}")

    lines.append("")

    # Risk assessment
    max_dd = abs(m.get("max_drawdown", 0))
    if max_dd > 0.3:
        lines.append("**风险警告** — 最大回撤超过 30%，建议降低集中度或增加风控约束。")
    elif max_dd > 0.2:
        lines.append("**风险提示** — 最大回撤在 20-30% 之间，属于较高风险水平。")

    return "\n".join(lines)
