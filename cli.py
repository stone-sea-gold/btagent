"""AIFUND5 CLI — natural language interface to the quant agent.

Usage:
    python cli.py              # Start interactive session
    python cli.py --init-data  # Download Qlib data and load builtin factors
    python cli.py --session <id>  # Resume a specific session
"""

import argparse
import traceback

from langchain_core.messages import AIMessage, HumanMessage

from src.agent.graph import create_agent_graph, create_session
from src.config import settings
from src.core.backtest_engine import BacktestEngine
from src.core.factor_store import FactorStore
from src.core.session_store import SessionStore
from src.core.strategy_compiler import StrategyCompiler
from src.core.position_manager import PositionManager
from src.core.param_optimizer import ParamOptimizer
from src.core.stock_selector import StockSelector
from src.exceptions import AIFundError
from src.logging import configure_logging, get_logger
from src.tools.storage_tools import StrategyStore


def init_data():
    """Download Qlib data and load builtin factors."""
    print("正在初始化数据...")

    print("  下载 Qlib A 股数据...")
    from src.data.qlib_setup import download_qlib_data
    download_qlib_data()
    print("  Qlib 数据下载完成")

    print("  加载内置因子库...")
    store = FactorStore()
    count = store.load_builtin_factors()
    print(f"  已加载 {count} 个内置因子")
    store.close()

    print("初始化完成!")


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
    logger.info("cli_session_end", session_id=session_id)


def main():
    parser = argparse.ArgumentParser(description="AIFUND5 — A股量化投资助手")
    parser.add_argument("--init-data", action="store_true", help="下载 Qlib 数据并加载内置因子")
    parser.add_argument("--session", type=str, help="恢复指定会话 ID")
    args = parser.parse_args()

    if args.init_data:
        init_data()
    else:
        run_cli(session_id=args.session)


if __name__ == "__main__":
    main()
