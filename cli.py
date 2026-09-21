"""AIFUND5 CLI — natural language interface to the quant agent.

Usage:
    python cli.py              # Start interactive session
    python cli.py --session <id>  # Resume a specific session
    python cli.py --sync-data --index csi300 --years 1   # Pull market data
    python cli.py --export-qlib   # Export the warehouse for the backtest engine
"""

import argparse
import traceback

from langchain_core.messages import AIMessage, HumanMessage

from src.agent.graph import create_agent_graph, create_session
from src.config import settings
from src.core.backtest_engine import BacktestEngine
from src.core.factor_store import FactorStore
from src.core.param_optimizer import ParamOptimizer
from src.core.position_manager import PositionManager
from src.core.session_store import SessionStore
from src.core.stock_selector import StockSelector
from src.core.strategy_compiler import StrategyCompiler
from src.data.providers import close_providers
from src.data.sync import DEFAULT_YEARS
from src.exceptions import AIFundError
from src.logging import configure_logging, get_logger
from src.tools.storage_tools import StrategyStore


def run_cli(session_id: str | None = None):
    """Run the interactive CLI."""
    configure_logging(settings.log_level)
    logger = get_logger("cli")

    # Initialize components
    print("正在初始化 AIFUND5...")
    factor_store = FactorStore()
    factor_store.load_builtin_factors(force_update=True)
    strategy_compiler = StrategyCompiler(factor_store=factor_store)
    backtest_engine = BacktestEngine()
    strategy_store = StrategyStore()
    session_store = SessionStore()
    position_manager = PositionManager()
    param_optimizer = ParamOptimizer(
        strategy_compiler=strategy_compiler,
        backtest_engine=backtest_engine,
        strategy_store=strategy_store,
    )
    stock_selector = StockSelector(factor_store=factor_store)

    # Session management
    if session_id:
        # Resume existing session
        try:
            session = session_store.load(session_id)
            print(f"恢复会话: {session['name']} ({session_id})")
        except Exception:
            print(f"会话 '{session_id}' 不存在，创建新会话")
            session_id = create_session(session_store)
    else:
        # Show existing sessions or create new one
        sessions = session_store.list_active()
        if sessions:
            print("\n已有会话:")
            for s in sessions[:5]:
                print(f"  [{s['session_id']}] {s['name']} (更新于 {s['updated_at'][:16]})")
            print()

        session_id = create_session(session_store)

    logger.info("cli_session_start", session_id=session_id)

    # Create agent graph
    graph = create_agent_graph(
        factor_store=factor_store,
        strategy_compiler=strategy_compiler,
        backtest_engine=backtest_engine,
        strategy_store=strategy_store,
        session_store=session_store,
        position_manager=position_manager,
        param_optimizer=param_optimizer,
        stock_selector=stock_selector,
    )

    print(f"\n{'='*60}")
    print("  AIFUND5 — A股量化投资助手")
    print("  输入策略描述，我来帮你回测")
    print()
    print("  命令:")
    print("    /new        — 新建会话（清除上下文）")
    print("    /sessions   — 查看所有会话")
    print("    /switch <id> — 切换到指定会话")
    print("    quit/exit   — 退出")
    print(f"\n  当前会话: {session_id}")
    print(f"{'='*60}\n")

    messages = []

    while True:
        try:
            user_input = input("你: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见!")
            break

        if not user_input:
            continue

        if user_input.lower() in ("quit", "exit", "q"):
            print("再见!")
            break

        # Slash commands
        if user_input.lower() == "/new":
            session_id = create_session(session_store)
            messages = []
            print(f"\n新会话已创建: {session_id}\n")
            continue

        if user_input.lower() == "/sessions":
            sessions = session_store.list_active()
            if sessions:
                print("\n活跃会话:")
                for s in sessions:
                    marker = " ← 当前" if s["session_id"] == session_id else ""
                    print(f"  [{s['session_id']}] {s['name']}{marker}")
            else:
                print("\n没有活跃会话")
            print()
            continue

        if user_input.lower().startswith("/switch "):
            target_id = user_input[8:].strip()
            try:
                session_store.load(target_id)
                session_id = target_id
                messages = []
                print(f"\n已切换到会话: {session_id}\n")
            except Exception:
                print(f"\n会话 '{target_id}' 不存在\n")
            continue

        messages.append(HumanMessage(content=user_input))

        try:
            result = graph.invoke({
                "messages": messages,
                "session_id": session_id,
                "current_strategy": None,
                "last_backtest_result": None,
                "tool_call_log": [],
            })

            agent_messages = result["messages"]
            for msg in reversed(agent_messages):
                if isinstance(msg, AIMessage) and msg.content and not msg.tool_calls:
                    print(f"\n助手: {msg.content}\n")
                    break

            messages = result["messages"]

        except AIFundError as e:
            logger.error("agent_error", error=str(e), details=e.details)
            print(f"\n错误: {e.message}\n")

        except Exception as e:
            logger.error("unexpected_error", error=str(e), traceback=traceback.format_exc())
            print(f"\n意外错误: {e}\n")

    # Cleanup
    factor_store.close()
    backtest_engine.close()
    strategy_store.close()
    session_store.close()
    close_providers()
    logger.info("cli_session_end", session_id=session_id)


def sync_market_data(
    *,
    index: str | None = None,
    codes: str | None = None,
    start: str | None = None,
    end: str | None = None,
    years: int = DEFAULT_YEARS,
    source: str | None = None,
    no_resume: bool = False,
    no_factors: bool = False,
) -> int:
    """Pull market data from an external source into the local warehouse.

    Returns a process exit code.
    """
    from datetime import date, timedelta

    from src.data.providers import PROVIDERS, get_provider
    from src.data.store import MarketStore
    from src.data.sync import sync_universe

    # A trading window is bounded by exchange calendar dates, not instants.
    today = date.today()  # noqa: DTZ011
    window_end = date.fromisoformat(end) if end else today
    window_start = date.fromisoformat(start) if start else window_end - timedelta(days=365 * years)

    selected = [c.strip() for c in codes.split(",") if c.strip()] if codes else None
    source_name = source or settings.data_source_priority.split(",")[0].strip()

    if source_name not in PROVIDERS:
        print(f"未知数据源 {source_name!r}；可用：{', '.join(sorted(PROVIDERS))}")
        return 2

    print(f"数据源：{source_name}")
    print(f"区间：{window_start} → {window_end}")
    print(f"范围：{'代码 ' + ','.join(selected) if selected else '指数 ' + (index or 'csi300')}")

    provider = get_provider(source_name)
    try:
        with MarketStore() as store:
            def report(done: int, total: int, code: str, rows: int) -> None:
                print(f"  [{done}/{total}] {code}  {rows} 根", flush=True)

            result = sync_universe(
                store,
                provider,
                window_start,
                window_end,
                index=index if not selected else None,
                codes=selected,
                resume=not no_resume,
                with_factors=not no_factors,
                progress=report,
            )
            print(f"\n{result.summary()}")
            if result.failures:
                print("失败明细：")
                for code, message in result.failures.items():
                    print(f"  {code}: {message}")
            coverage = store.coverage()
            print(
                f"仓库现状：{coverage['bars']:,} 根 bar · {coverage['codes']} 只 · "
                f"{coverage['first_date']} → {coverage['last_date']} · "
                f"{coverage['factor_rows']:,} 行复权因子"
            )
    except AIFundError as exc:
        print(f"同步失败：{exc.message}")
        return 1

    return 0 if result.ok else 1


def export_qlib_data(
    *,
    out: str | None = None,
    codes: str | None = None,
    start: str | None = None,
    end: str | None = None,
) -> int:
    """Export the warehouse as a Qlib dataset the backtest engine can read.

    ``out`` defaults to the directory the engine resolves, so ``--export-qlib``
    works without a path.
    """
    from datetime import date as _date

    from src.data.qlib_export import write_qlib_dataset
    from src.data.store import MarketStore

    target = out or settings.qlib_export_path
    window_start = _date.fromisoformat(start) if start else None
    window_end = _date.fromisoformat(end) if end else None
    selected = [c.strip() for c in codes.split(",") if c.strip()] if codes else None

    try:
        excluded = [] if selected else [settings.benchmark_code]
        with MarketStore() as store:
            counts = write_qlib_dataset(
                store, target, selected, window_start, window_end,
                exclude_from_universe=excluded,
            )
    except AIFundError as exc:
        print(f"导出失败：{exc.message}")
        return 1
    print(f"已导出 Qlib 数据集 → {target}")
    print(
        f"  交易域 {counts['instruments']} 只 · 特征文件 {counts['features']} 只 · "
        f"{counts['days']} 个交易日 · {counts['fields']} 个字段"
    )
    return 0


def main():
    parser = argparse.ArgumentParser(description="AIFUND5 — A股量化投资助手")
    parser.add_argument("--session", type=str, help="恢复指定会话 ID")

    data = parser.add_argument_group("市场数据同步")
    data.add_argument("--sync-data", action="store_true", help="从外部数据源拉取行情到本地仓库")
    data.add_argument("--index", type=str, help="指数名，如 csi300 / csi500 / sse50")
    data.add_argument("--codes", type=str, help="逗号分隔的股票代码，优先于 --index")
    data.add_argument("--start", type=str, help="起始日期 YYYY-MM-DD")
    data.add_argument("--end", type=str, help="结束日期 YYYY-MM-DD（默认今天）")
    data.add_argument("--years", type=int, default=DEFAULT_YEARS, help=f"未指定 --start 时的回溯年数（默认 {DEFAULT_YEARS}）")
    data.add_argument("--source", type=str, help="数据源名，默认取 data_source_priority 的第一项")
    data.add_argument("--no-resume", action="store_true", help="忽略已同步区间，强制重新拉取")
    data.add_argument("--no-factors", action="store_true", help="不拉取复权因子")
    exp = parser.add_argument_group("Qlib 数据集导出")
    exp.add_argument(
        "--export-qlib",
        nargs="?",
        const="",
        default=None,
        metavar="OUT_DIR",
        help="将仓库行情导出为 Qlib bin 数据集（省略 OUT_DIR 时导出到默认目录）",
    )
    args = parser.parse_args()

    if args.export_qlib is not None:
        return export_qlib_data(
            out=args.export_qlib or None, codes=args.codes, start=args.start, end=args.end
        )
    if args.sync_data:
        return sync_market_data(
            index=args.index,
            codes=args.codes,
            start=args.start,
            end=args.end,
            years=args.years,
            source=args.source,
            no_resume=args.no_resume,
            no_factors=args.no_factors,
        )
    run_cli(session_id=args.session)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
