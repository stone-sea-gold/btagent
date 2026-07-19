"""Backtest tools for the Agent."""

from src.core.backtest_engine import BacktestEngine
from src.core.models import StrategyConfig
from src.core.strategy_compiler import StrategyCompiler
from src.exceptions import BacktestError
from src.logging import get_logger

logger = get_logger("backtest_tools")


def _get_error_action(error_type: str, details: dict) -> str:
    """Return actionable guidance based on error type."""
    if error_type == "import_error":
        module = details.get("module", "unknown")
        return f"Qlib 模块 ({module}) 导入失败。请运行: pip install pyqlib"
    if error_type == "data_empty":
        return "Qlib 数据为空。请运行: python cli.py --init-data --force"
    if error_type == "date_out_of_range":
        data_end = details.get("data_end", "未知")
        data_start = details.get("data_start", "未知")
        return (
            f"日期超出数据范围。当前数据覆盖: {data_start} ~ {data_end}。"
            f"请将回测日期调整到此范围内，或运行 python cli.py --init-data --force 更新数据。"
        )
    if error_type == "data_error":
        return "回测数据无效。请运行: python cli.py --init-data --force 重新下载数据。"
    if error_type == "runtime_error":
        return f"回测运行异常 ({details.get('exception_type', '')})。请检查日期范围和策略参数是否合理。"
    return "请检查回测参数是否正确，或查看后端日志获取详细信息。"


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
    except Exception as e:
        logger.error("strategy_config_invalid", error=str(e))
        return {
            "status": "error",
            "error_type": "invalid_config",
            "error": f"策略配置无效: {e}",
            "action": "请检查策略配置字段是否完整（name, factor_ids, start_date, end_date 为必填项）",
        }

    try:
        compiled = compiler.compile(config)
    except Exception as e:
        logger.error("strategy_compile_error", error=str(e))
        return {
            "status": "error",
            "error_type": "compile_error",
            "error": f"策略编译失败: {e}",
            "action": "请检查因子 ID 是否正确。使用 search_factors 工具搜索可用因子。",
        }

    try:
        result = engine.run(
            strategy_id=config.name,
            compiled_strategy=compiled,
            start_date=config.start_date,
            end_date=config.end_date,
            benchmark=config.benchmark,
        )
    except BacktestError as e:
        logger.error("run_backtest_error", error=str(e), details=e.details)
        error_type = e.details.get("error_type", "unknown")
        action = _get_error_action(error_type, e.details)
        return {
            "status": "error",
            "error_type": error_type,
            "error": e.message,
            "action": action,
        }
    except Exception as e:
        logger.error("run_backtest_error", error=str(e))
        return {
            "status": "error",
            "error_type": "unknown",
            "error": str(e),
            "action": "请检查后端日志获取详细错误信息。",
        }

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


def analyze_backtest(backtest_result: dict) -> str:
    """Generate structured analysis of backtest results.

    Args:
        backtest_result: Result dict from run_backtest.

    Returns:
        Structured Markdown analysis with rating and suggestions.
    """
    if backtest_result.get("status") != "success":
        return f"回测未能成功完成：{backtest_result.get('error', '未知错误')}"

    m = backtest_result.get("metrics", {})
    name = backtest_result.get("strategy_name", "策略")

    total_return = m.get("total_return", 0)
    annualized_return = m.get("annualized_return", 0)
    sharpe = m.get("sharpe_ratio", 0)
    max_dd = abs(m.get("max_drawdown", 0))
    volatility = m.get("volatility", 0)
    win_rate = m.get("win_rate", 0)
    dd_duration = m.get("max_drawdown_duration", 0)

    # Derived metrics
    calmar = annualized_return / max_dd if max_dd > 0 else 0.0
    return_dd_ratio = total_return / max_dd if max_dd > 0 else 0.0

    # Rating
    if sharpe > 1.5 and max_dd < 0.15 and annualized_return > 0.15:
        rating = "A（优秀）"
        rating_desc = "风险调整后收益显著，回撤控制良好。"
    elif sharpe > 0.8 and max_dd < 0.25:
        rating = "B（良好）"
        rating_desc = "具有超额收益能力，风险可控。"
    elif sharpe > 0 and max_dd < 0.35:
        rating = "C（一般）"
        rating_desc = "收益与风险基本匹配，有改进空间。"
    else:
        rating = "D（不佳）"
        rating_desc = "策略可能存在问题，需要重新审视。"

    lines = [f"## {name} 回测分析\n"]

    # Rating
    lines.append(f"### 综合评级：{rating}")
    lines.append(f"{rating_desc}\n")

    # Return analysis
    lines.append("### 收益分析")
    lines.append(f"| 指标 | 数值 |")
    lines.append(f"|------|------|")
    lines.append(f"| 总收益率 | {total_return:.2%} |")
    lines.append(f"| 年化收益率 | {annualized_return:.2%} |")
    lines.append(f"| 夏普比率 | {sharpe:.2f} |")
    lines.append(f"| Calmar 比率 | {calmar:.2f} |")
    lines.append("")

    # Risk analysis
    lines.append("### 风险分析")
    lines.append(f"| 指标 | 数值 |")
    lines.append(f"|------|------|")
    lines.append(f"| 最大回撤 | {max_dd:.2%} |")
    lines.append(f"| 年化波动率 | {volatility:.2%} |")
    lines.append(f"| 收益回撤比 | {return_dd_ratio:.2f} |")
    if dd_duration > 0:
        lines.append(f"| 最长回撤期 | {dd_duration} 天 |")
    lines.append("")

    # Efficiency
    lines.append("### 效率指标")
    lines.append(f"| 指标 | 数值 |")
    lines.append(f"|------|------|")
    lines.append(f"| 胜率 | {win_rate:.2%} |")
    lines.append(f"| 夏普比率 | {sharpe:.2f} |")
    lines.append(f"| Calmar 比率 | {calmar:.2f} |")
    lines.append("")

    # Risk warnings
    if max_dd > 0.3:
        lines.append("### ⚠️ 风险警告")
        lines.append("- 最大回撤超过 30%，建议降低集中度或增加风控约束。")
    elif max_dd > 0.2:
        lines.append("### ⚠️ 风险提示")
        lines.append("- 最大回撤在 20-30% 之间，属于较高风险水平。")

    if volatility > 0.3:
        lines.append("- 年化波动率超过 30%，策略波动较大。")

    lines.append("")

    # Suggestions
    lines.append("### 改进建议")
    suggestions = []
    if max_dd > 0.25:
        suggestions.append("回撤过大：建议降低单票集中度，增加持仓分散度，或添加止损规则。")
    if sharpe < 0.5:
        suggestions.append("夏普比率偏低：建议优化因子选择，或调整调仓频率以降低交易成本。")
    if win_rate < 0.4:
        suggestions.append("胜率较低：建议增加过滤条件，提高选股精度。")
    if volatility > 0.25:
        suggestions.append("波动率较高：建议增加低波动因子权重，或减小仓位集中度。")
    if calmar < 0.5 and annualized_return > 0:
        suggestions.append("收益回撤比不佳：建议优化止盈止损策略，控制回撤幅度。")
    if not suggestions:
        suggestions.append("策略表现均衡，可考虑通过参数优化进一步提升。")

    for s in suggestions:
        lines.append(f"- {s}")

    return "\n".join(lines)
