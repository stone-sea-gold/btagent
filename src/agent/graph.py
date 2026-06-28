"""LangGraph agent graph for AIFUND5.

Architecture:
- Single agent with tools (not multi-agent)
- Stateful graph with tool execution loop
- Structured logging of every tool call
- Session persistence via SessionStore
"""

from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode

from src.agent.state import AgentState
from src.config import settings
from src.llm_factory import create_llm
from src.core.backtest_engine import BacktestEngine
from src.core.factor_store import FactorStore
from src.core.session_store import SessionStore
from src.core.strategy_compiler import StrategyCompiler
from src.exceptions import AgentError, LLMError
from src.logging import get_logger, new_session_id
from src.tools.backtest_tools import analyze_backtest, run_backtest
from src.tools.comparison_tools import compare_strategies, update_strategy
from src.tools.factor_tools import create_factor, search_factors
from src.tools.storage_tools import (
    StrategyStore,
    list_strategies,
    load_strategy,
    save_strategy,
    search_strategies,
)
from src.tools.strategy_tools import compose_strategy
from src.tools.selection_tools import select_stocks as _select_stocks_fn
from src.tools.position_tools import (
    save_holdings as _save_holdings_fn,
    get_portfolio_status as _get_portfolio_status_fn,
    save_position_rules as _save_position_rules_fn,
)
from src.tools.optimize_tools import optimize_parameters as _optimize_parameters_fn
from src.tools.stoploss_tools import (
    add_stoploss_rules as _add_stoploss_rules_fn,
    run_backtest_with_stoploss as _run_backtest_with_stoploss_fn,
    check_stoploss_scenarios as _check_stoploss_scenarios_fn,
)
from src.core.position_manager import PositionManager
from src.core.param_optimizer import ParamOptimizer
from src.core.stock_selector import StockSelector
from src.tools.calendar_tools import (
    get_current_date as _get_current_date_fn,
    resolve_relative_date as _resolve_relative_date_fn,
    get_trading_days as _get_trading_days_fn,
)
from src.tools.data_tools import check_data_coverage as _check_data_coverage_fn

logger = get_logger("agent_graph")


def create_agent_graph(
    factor_store: FactorStore,
    strategy_compiler: StrategyCompiler,
    backtest_engine: BacktestEngine,
    strategy_store: StrategyStore,
    session_store: SessionStore,
    position_manager: PositionManager = None,
    param_optimizer: ParamOptimizer = None,
    stock_selector: StockSelector = None,
    checkpointer=None,
) -> StateGraph:
    """Create the LangGraph agent graph.

    Returns:
        Compiled LangGraph StateGraph.
    """

    # ── Tool functions with bound dependencies ─────────────────────

    def _search_factors(query: str) -> str:
        """Search the factor library by natural language query."""
        import json
        results = search_factors(query, factor_store)
        return json.dumps(results, ensure_ascii=False, indent=2)

    def _create_factor(
        id: str, name: str, description: str, category: str, formula: str,
        tags: str = "",
    ) -> str:
        """Create a new custom factor."""
        import json
        tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []
        result = create_factor(
            id=id, name=name, description=description,
            category=category, formula=formula,
            factor_store=factor_store, tags=tag_list,
        )
        return json.dumps(result, ensure_ascii=False, indent=2)

    def _compose_strategy(
        name: str, factor_ids: str, start_date: str, end_date: str,
        selection_rule: str = "top_k", max_holding: int = 10,
        rebalance_freq: str = "monthly", weight_scheme: str = "equal",
    ) -> str:
        """Compose a strategy from factors. Validates factor IDs exist."""
        import json
        from src.exceptions import FactorNotFoundError

        fid_list = [f.strip() for f in factor_ids.split(",") if f.strip()]

        invalid_ids = []
        for fid in fid_list:
            try:
                factor_store.get(fid)
            except FactorNotFoundError:
                invalid_ids.append(fid)

        if invalid_ids:
            available = [f.id for f in factor_store.list_all()]
            return json.dumps({
                "error": f"因子 ID 不存在: {invalid_ids}",
                "available_factor_ids": available,
                "hint": "请使用 search_factors 搜索正确的因子 ID",
                "status": "invalid_factor_ids",
            }, ensure_ascii=False, indent=2)

        result = compose_strategy(
            name=name, factor_ids=fid_list,
            start_date=start_date, end_date=end_date,
            selection_rule=selection_rule, max_holding=max_holding,
            rebalance_freq=rebalance_freq, weight_scheme=weight_scheme,
        )
        return json.dumps(result, ensure_ascii=False, indent=2)

    def _run_backtest(strategy_config_json: str) -> str:
        """Run a backtest with the given strategy config JSON."""
        import json
        config = json.loads(strategy_config_json)
        result = run_backtest(config, strategy_compiler, backtest_engine)
        return json.dumps(result, ensure_ascii=False, indent=2)

    def _analyze_backtest(backtest_result_json: str) -> str:
        """Analyze backtest results and generate natural language summary."""
        import json
        result = json.loads(backtest_result_json)
        return analyze_backtest(result)

    def _save_strategy(
        name: str, config_json: str, description: str = "",
        agent_summary: str = "", version: int = 1, parent_id: str = "",
    ) -> str:
        """Save a strategy to persistent storage with version chain."""
        import json
        config = json.loads(config_json)
        result = save_strategy(
            name, config, strategy_store, description,
            agent_summary=agent_summary, version=version,
            parent_id=parent_id or None,
        )
        return json.dumps(result, ensure_ascii=False, indent=2)

    def _load_strategy(strategy_id: str) -> str:
        """Load a saved strategy by ID."""
        import json
        result = load_strategy(strategy_id, strategy_store)
        return json.dumps(result, ensure_ascii=False, indent=2)

    def _list_strategies() -> str:
        """List all saved strategies."""
        import json
        result = list_strategies(strategy_store)
        return json.dumps(result, ensure_ascii=False, indent=2)

    def _search_strategies(query: str) -> str:
        """Search strategies by semantic similarity."""
        import json
        results = search_strategies(query, strategy_store)
        return json.dumps(results, ensure_ascii=False, indent=2)

    def _compare_strategies(strategy_ids: str) -> str:
        """Compare multiple strategies side-by-side."""
        import json
        ids = [s.strip() for s in strategy_ids.split(",") if s.strip()]
        result = compare_strategies(ids, strategy_store)
        return json.dumps(result, ensure_ascii=False, indent=2)

    def _update_strategy(strategy_id: str, modifications_json: str, agent_summary: str = "") -> str:
        """Update a strategy by creating a new version."""
        import json
        modifications = json.loads(modifications_json)
        result = update_strategy(strategy_id, modifications, strategy_store, agent_summary)
        return json.dumps(result, ensure_ascii=False, indent=2)

    def _get_version_chain(strategy_id: str) -> str:
        """Get the full version chain for a strategy."""
        import json
        chain = strategy_store.get_version_chain(strategy_id)
        return json.dumps(chain, ensure_ascii=False, indent=2)

    # ── Phase 3 tool functions ────────────────────────────────────

    def _select_stocks(
        name: str, factor_ids: str, top_k: int = 50,
        factor_weights_json: str = "", filter_conditions_json: str = "",
        universe: str = "csi300", date: str = "",
    ) -> str:
        """Run stock selection pipeline."""
        import json
        result = _select_stocks_fn(
            name=name, factor_ids=factor_ids, top_k=top_k,
            factor_weights_json=factor_weights_json,
            filter_conditions_json=filter_conditions_json,
            universe=universe, date=date, selector=stock_selector,
        )
        return json.dumps(result, ensure_ascii=False, indent=2)

    def _save_holdings(session_id: str, holdings_json: str) -> str:
        """Save portfolio holdings."""
        import json
        result = _save_holdings_fn(session_id, holdings_json, position_manager)
        return json.dumps(result, ensure_ascii=False, indent=2)

    def _get_portfolio_status(session_id: str) -> str:
        """Get portfolio status and check rule violations."""
        import json
        result = _get_portfolio_status_fn(session_id, position_manager)
        return json.dumps(result, ensure_ascii=False, indent=2)

    def _save_position_rules(session_id: str, rules_json: str) -> str:
        """Save position management rules."""
        import json
        result = _save_position_rules_fn(session_id, rules_json, position_manager)
        return json.dumps(result, ensure_ascii=False, indent=2)

    def _optimize_parameters(
        strategy_id: str, method: str = "bayesian",
        param_ranges_json: str = "", metric: str = "sharpe_ratio",
        n_trials: int = 50, start_date: str = "", end_date: str = "",
    ) -> str:
        """Run parameter optimization."""
        import json
        result = _optimize_parameters_fn(
            strategy_id=strategy_id, method=method,
            param_ranges_json=param_ranges_json, metric=metric,
            n_trials=n_trials, start_date=start_date, end_date=end_date,
            optimizer=param_optimizer,
        )
        return json.dumps(result, ensure_ascii=False, indent=2)

    def _add_stoploss_rules(strategy_config_json: str, rules_json: str) -> str:
        """Add stop-loss rules to a strategy config."""
        import json
        result = _add_stoploss_rules_fn(strategy_config_json, rules_json)
        return json.dumps(result, ensure_ascii=False, indent=2)

    def _run_backtest_with_stoploss(strategy_config_json: str, stoploss_rules_json: str) -> str:
        """Run backtest with stop-loss rules."""
        import json
        result = _run_backtest_with_stoploss_fn(
            strategy_config_json, stoploss_rules_json,
            compiler=strategy_compiler, engine=backtest_engine,
        )
        return json.dumps(result, ensure_ascii=False, indent=2)

    def _check_stoploss_scenarios(strategy_config_json: str, stoploss_rules_json: str) -> str:
        """Analyze stop-loss trigger scenarios."""
        import json
        result = _check_stoploss_scenarios_fn(
            strategy_config_json, stoploss_rules_json,
            compiler=strategy_compiler, engine=backtest_engine,
        )
        return json.dumps(result, ensure_ascii=False, indent=2)

    # ── Calendar tool functions ───────────────────────────────────

    def _get_current_date() -> str:
        """Get today's date and the latest trading day."""
        return _get_current_date_fn()

    def _resolve_relative_date(expression: str, reference_date: str = "") -> str:
        """Resolve a relative date expression to absolute date(s)."""
        return _resolve_relative_date_fn(expression, reference_date)

    def _get_trading_days(start_date: str, end_date: str) -> str:
        """Get all trading days in a date range."""
        return _get_trading_days_fn(start_date, end_date)

    def _check_data_coverage() -> str:
        """Check Qlib data coverage and freshness."""
        return _check_data_coverage_fn()

    # ── Bind tools ─────────────────────────────────────────────────

    tools = [
        _search_factors,
        _create_factor,
        _compose_strategy,
        _run_backtest,
        _analyze_backtest,
        _save_strategy,
        _load_strategy,
        _list_strategies,
        _search_strategies,
        _compare_strategies,
        _update_strategy,
        _get_version_chain,
        _select_stocks,
        _save_holdings,
        _get_portfolio_status,
        _save_position_rules,
        _optimize_parameters,
        _add_stoploss_rules,
        _run_backtest_with_stoploss,
        _check_stoploss_scenarios,
        _get_current_date,
        _resolve_relative_date,
        _get_trading_days,
        _check_data_coverage,
    ]

    # Load system prompt
    prompt_path = Path(__file__).parent / "prompts" / "system.md"
    system_prompt = prompt_path.read_text(encoding="utf-8")

    # ── Graph nodes ────────────────────────────────────────────────

    def _get_llm():
        """Create a fresh LLM every call so DB config overrides take effect immediately."""
        return create_llm().bind_tools(tools)

    def agent_node(state: AgentState) -> dict:
        """Main agent node — calls LLM with tools."""
        messages = state["messages"]

        logger.info("agent_node_debug", msg_count=len(messages), msg_types=str([type(m).__name__ for m in messages[:3]]))

        if not messages or not isinstance(messages[0], SystemMessage):
            messages = [SystemMessage(content=system_prompt)] + messages

        try:
            response = _get_llm().invoke(messages)
            # Normalize content: if the LLM returns content blocks (list)
            # instead of a plain string, extract just the text portions.
            if isinstance(response.content, list):
                texts = []
                for block in response.content:
                    if isinstance(block, dict):
                        texts.append(block.get("text") or block.get("thinking") or "")
                    else:
                        texts.append(str(block))
                response.content = "\n".join(t for t in texts if t)
            logger.info(
                "agent_llm_response",
                has_tool_calls=bool(response.tool_calls),
                content_length=len(response.content) if response.content else 0,
            )
            return {"messages": [response]}
        except Exception as e:
            logger.error("agent_llm_error", error=str(e))
            msg = str(e)
            if "401" in msg or "unauthorized" in msg.lower() or "api_key" in msg.lower():
                hint = "API Key 无效或未设置，请前往设置页面检查 LLM 配置。"
            elif "402" in msg or "insufficient_quota" in msg or "insufficient balance" in msg.lower():
                hint = "API 额度不足，请检查账户余额。"
            elif "403" in msg or "forbidden" in msg.lower():
                hint = "API 权限不足或被禁止访问。"
            elif "404" in msg or "not found" in msg.lower():
                hint = "API 端点或模型名称不存在，请检查 Base URL 和 Model 名称。"
            elif "timeout" in msg.lower():
                hint = "请求超时，请检查网络连接或 Base URL 是否正确。"
            elif "rate" in msg.lower() and "limit" in msg.lower():
                hint = "请求频率过高，请稍后重试。"
            elif "at least one message" in msg:
                hint = "LLM 配置异常，协议检测可能不匹配。请尝试更换 Base URL 格式（OpenAI / Anthropic）。"
            else:
                hint = f"LLM 调用失败: {msg[:200]}"
            raise LLMError(hint) from e

    def should_continue(state: AgentState) -> str:
        last_message = state["messages"][-1]
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            return "tools"
        return END

    def tool_node_with_logging(state: AgentState) -> dict:
        """Execute tools one by one with structured logging."""
        last_message = state["messages"][-1]
        if not hasattr(last_message, "tool_calls"):
            return {"messages": []}

        import time
        from langchain_core.messages import ToolMessage

        # Build tool name -> underlying function mapping
        tool_func_map = {
            "_search_factors": _search_factors,
            "_create_factor": _create_factor,
            "_compose_strategy": _compose_strategy,
            "_run_backtest": _run_backtest,
            "_analyze_backtest": _analyze_backtest,
            "_save_strategy": _save_strategy,
            "_load_strategy": _load_strategy,
            "_list_strategies": _list_strategies,
            "_search_strategies": _search_strategies,
            "_compare_strategies": _compare_strategies,
            "_update_strategy": _update_strategy,
            "_get_version_chain": _get_version_chain,
            "_select_stocks": _select_stocks,
            "_save_holdings": _save_holdings,
            "_get_portfolio_status": _get_portfolio_status,
            "_save_position_rules": _save_position_rules,
            "_optimize_parameters": _optimize_parameters,
            "_add_stoploss_rules": _add_stoploss_rules,
            "_run_backtest_with_stoploss": _run_backtest_with_stoploss,
            "_check_stoploss_scenarios": _check_stoploss_scenarios,
            "_get_current_date": _get_current_date,
            "_resolve_relative_date": _resolve_relative_date,
            "_get_trading_days": _get_trading_days,
            "_check_data_coverage": _check_data_coverage,
        }

        results = []
        for tc in last_message.tool_calls:
            tool_name = tc["name"]
            tool_args = tc["args"]
            tool_call_id = tc["id"]

            logger.info("tool_call_start", tool=tool_name, args=tool_args)
            start = time.monotonic()

            try:
                func = tool_func_map.get(tool_name)
                if not func:
                    raise ToolExecutionError(f"Unknown tool: {tool_name}")

                # Call the function directly with keyword arguments
                output = func(**tool_args)
                duration_ms = (time.monotonic() - start) * 1000
                logger.info("tool_call_complete", tool=tool_name, duration_ms=round(duration_ms, 1))
                results.append(ToolMessage(content=str(output), tool_call_id=tool_call_id))

            except Exception as e:
                duration_ms = (time.monotonic() - start) * 1000
                logger.error("tool_call_error", tool=tool_name, error=str(e), duration_ms=round(duration_ms, 1))
                results.append(ToolMessage(content=f"Error: {e}", tool_call_id=tool_call_id))

        return {"messages": results}

    # ── Build graph ────────────────────────────────────────────────

    graph = StateGraph(AgentState)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", tool_node_with_logging)
    graph.set_entry_point("agent")
    graph.add_conditional_edges("agent", should_continue, {"tools": "tools", END: END})
    graph.add_edge("tools", "agent")

    return graph.compile(checkpointer=checkpointer)


def create_session(session_store: SessionStore | None = None) -> str:
    """Create a new agent session and return the session ID."""
    sid = new_session_id()
    if session_store:
        session_store.create(name=f"session_{sid}")
    logger.info("session_created", session_id=sid)
    return sid
