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

logger = get_logger("agent_graph")


def create_agent_graph(
    factor_store: FactorStore,
    strategy_compiler: StrategyCompiler,
    backtest_engine: BacktestEngine,
    strategy_store: StrategyStore,
    session_store: SessionStore,
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
    ]

    # Create LLM via factory
    llm = create_llm().bind_tools(tools)

    # Load system prompt
    prompt_path = Path(__file__).parent / "prompts" / "system.md"
    system_prompt = prompt_path.read_text(encoding="utf-8")

    # ── Graph nodes ────────────────────────────────────────────────

    def agent_node(state: AgentState) -> dict:
        """Main agent node — calls LLM with tools."""
        messages = state["messages"]

        if not messages or not isinstance(messages[0], SystemMessage):
            messages = [SystemMessage(content=system_prompt)] + messages

        try:
            response = llm.invoke(messages)
            logger.info(
                "agent_llm_response",
                has_tool_calls=bool(response.tool_calls),
                content_length=len(response.content) if response.content else 0,
            )
            return {"messages": [response]}
        except Exception as e:
            logger.error("agent_llm_error", error=str(e))
            raise LLMError(f"Agent LLM call failed: {e}") from e

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

    return graph.compile()


def create_session(session_store: SessionStore | None = None) -> str:
    """Create a new agent session and return the session ID."""
    sid = new_session_id()
    if session_store:
        session_store.create(name=f"session_{sid}")
    logger.info("session_created", session_id=sid)
    return sid
