"""LangGraph agent graph for AIFUND5.

Architecture:
- Single agent with tools (not multi-agent)
- Two-node ReAct loop: the model decides, then its tool calls execute, repeat
- Tool surface is defined once in :mod:`src.agent.adapters` and discovered via
  :mod:`src.agent.registry`; this module no longer keeps its own tool list
- Structured logging of every tool call, with per-tool error isolation
- Session persistence via SessionStore

The graph is deliberately thin. Everything that describes *what the agent can
do* lives in the adapter modules; this file only wires the loop, the model, and
the system prompt together.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Iterable

from langchain_core.messages import SystemMessage, ToolMessage
from langgraph.graph import END, StateGraph

from src.agent.adapters import build_registry
from src.agent.deps import AgentDeps
from src.agent.state import AgentState
from src.core.backtest_engine import BacktestEngine
from src.core.factor_store import FactorStore
from src.core.param_optimizer import ParamOptimizer
from src.core.position_manager import PositionManager
from src.core.session_store import SessionStore
from src.core.stock_selector import StockSelector
from src.core.strategy_compiler import StrategyCompiler
from src.exceptions import LLMError, ToolExecutionError
from src.llm_factory import create_llm
from src.logging import get_logger, new_session_id
from src.tools.storage_tools import StrategyStore

logger = get_logger(__name__)

# Module-level LLM cache — shared across graph instances
_llm_cache: dict = {"key": None, "instance": None}

# Tools whose successful output becomes part of the session context.
_STRATEGY_TOOL = "_compose_strategy"
_BACKTEST_TOOL = "_run_backtest"


def invalidate_llm_cache() -> None:
    """Clear the cached LLM instance. Call after config changes."""
    _llm_cache["key"] = None
    _llm_cache["instance"] = None


def _llm_config_key() -> tuple:
    """Identity of the active LLM configuration, used as the cache key."""
    from src.config import settings
    from src.llm_factory import _load_override

    cfg = _load_override()
    if cfg and cfg.base_url and cfg.api_key and cfg.model:
        return (cfg.model, cfg.api_key, cfg.base_url)
    return (settings.llm_provider, settings.llm_api_key, settings.llm_model)


def _get_llm(tools: list):
    """Create or reuse an LLM instance. Reuses when config unchanged."""
    key = _llm_config_key()
    if _llm_cache["key"] == key and _llm_cache["instance"] is not None:
        return _llm_cache["instance"]

    llm = create_llm().bind_tools(tools)
    _llm_cache["key"] = key
    _llm_cache["instance"] = llm
    return llm


def _llm_error_hint(message: str) -> str:
    """Translate a provider error into an actionable Chinese hint.

    Checked in order; the first match wins, matching the previous inline chain.
    """
    lowered = message.lower()
    if "401" in message or "unauthorized" in lowered or "api_key" in lowered:
        return "API Key 无效或未设置，请前往设置页面检查 LLM 配置。"
    if "402" in message or "insufficient_quota" in message or "insufficient balance" in lowered:
        return "API 额度不足，请检查账户余额。"
    if "403" in message or "forbidden" in lowered:
        return "API 权限不足或被禁止访问。"
    if "404" in message or "not found" in lowered:
        return "API 端点或模型名称不存在，请检查 Base URL 和 Model 名称。"
    if "timeout" in lowered:
        return "请求超时，请检查网络连接或 Base URL 是否正确。"
    if "rate" in lowered and "limit" in lowered:
        return "请求频率过高，请稍后重试。"
    if "at least one message" in message:
        return "LLM 配置异常，协议检测可能不匹配。请尝试更换 Base URL 格式（OpenAI / Anthropic）。"
    return f"LLM 调用失败: {message[:200]}"


def _normalize_content(response) -> None:
    """Flatten content blocks into plain text, in place.

    Anthropic-style responses return a list of blocks rather than a string.
    """
    if not isinstance(response.content, list):
        return
    texts = []
    for block in response.content:
        if isinstance(block, dict):
            texts.append(block.get("text") or block.get("thinking") or "")
        else:
            texts.append(str(block))
    response.content = "\n".join(t for t in texts if t)


def _load_system_prompt() -> str:
    return (Path(__file__).parent / "prompts" / "system.md").read_text(encoding="utf-8")


def _session_context(tool_name: str, output: str) -> dict:
    """Derive session-context state from a successful tool result.

    Only the two tools with an unambiguous contract contribute. Anything that
    fails to parse is ignored rather than raising, so a malformed tool result
    can never break the loop.
    """
    if tool_name not in (_STRATEGY_TOOL, _BACKTEST_TOOL):
        return {}
    import json

    try:
        payload = json.loads(output)
    except (ValueError, TypeError):
        return {}
    if not isinstance(payload, dict) or payload.get("error"):
        return {}
    if tool_name == _STRATEGY_TOOL:
        return {"current_strategy": payload}
    return {"last_backtest_result": payload}


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
    domains: Iterable[str] | None = None,
) -> StateGraph:
    """Create the LangGraph agent graph.

    Args:
        domains: Optional capability-domain filter (e.g. ``["factor", "backtest"]``).
            When omitted every registered tool is exposed, which is the default
            behaviour. Narrowing the set shrinks the tool schema sent to the
            model, which improves tool selection at the cost of reach.

    Returns:
        Compiled LangGraph StateGraph.
    """
    deps = AgentDeps(
        factor_store=factor_store,
        strategy_compiler=strategy_compiler,
        backtest_engine=backtest_engine,
        strategy_store=strategy_store,
        session_store=session_store,
        position_manager=position_manager,
        param_optimizer=param_optimizer,
        stock_selector=stock_selector,
    )

    # The registry is the single source of truth: the list bound to the model
    # and the dispatch table used to execute its calls both derive from it, so
    # they cannot drift apart.
    registry = build_registry(deps)
    tools = registry.bind(domains)
    dispatch = registry.dispatch(domains)
    system_prompt = _load_system_prompt()

    logger.info(
        "agent_graph_created",
        tool_count=len(tools),
        domain_count=len(registry.domains()),
        domains=sorted(domains) if domains is not None else "all",
    )

    # ── Graph nodes ────────────────────────────────────────────────

    def agent_node(state: AgentState) -> dict:
        """Main agent node — calls LLM with tools."""
        messages = state["messages"]

        if not messages or not isinstance(messages[0], SystemMessage):
            messages = [SystemMessage(content=system_prompt)] + messages

        try:
            response = _get_llm(tools).invoke(messages)
            _normalize_content(response)
            logger.info(
                "agent_llm_response",
                has_tool_calls=bool(response.tool_calls),
                content_length=len(response.content) if response.content else 0,
            )
            return {"messages": [response]}
        except Exception as e:
            logger.error("agent_llm_error", error=str(e))
            raise LLMError(_llm_error_hint(str(e))) from e

    def should_continue(state: AgentState) -> str:
        last_message = state["messages"][-1]
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            return "tools"
        return END

    def tool_node(state: AgentState) -> dict:
        """Execute the model's tool calls, one at a time, isolating failures."""
        last_message = state["messages"][-1]
        if not hasattr(last_message, "tool_calls"):
            return {"messages": []}

        results: list[ToolMessage] = []
        log_entries: list[dict] = []
        context: dict = {}

        for tc in last_message.tool_calls:
            tool_name = tc["name"]
            tool_args = tc["args"]
            tool_call_id = tc["id"]

            logger.info("tool_call_start", tool=tool_name, args=tool_args)
            start = time.monotonic()

            try:
                func = dispatch.get(tool_name)
                if func is None:
                    raise ToolExecutionError(
                        f"Unknown tool: {tool_name}. "
                        f"Available tools: {', '.join(sorted(dispatch))}"
                    )

                output = func(**tool_args)
                duration_ms = round((time.monotonic() - start) * 1000, 1)
                logger.info("tool_call_complete", tool=tool_name, duration_ms=duration_ms)
                results.append(ToolMessage(content=str(output), tool_call_id=tool_call_id))
                log_entries.append(
                    {"tool": tool_name, "ok": True, "duration_ms": duration_ms}
                )
                context.update(_session_context(tool_name, str(output)))

            except Exception as e:
                # One bad tool call must not abort the run: hand the error back
                # to the model so it can retry or choose another tool.
                duration_ms = round((time.monotonic() - start) * 1000, 1)
                logger.error(
                    "tool_call_error",
                    tool=tool_name,
                    error=str(e),
                    duration_ms=duration_ms,
                )
                results.append(ToolMessage(content=f"Error: {e}", tool_call_id=tool_call_id))
                log_entries.append(
                    {
                        "tool": tool_name,
                        "ok": False,
                        "error": str(e),
                        "duration_ms": duration_ms,
                    }
                )

        return {"messages": results, "tool_call_log": log_entries, **context}

    # ── Build graph ────────────────────────────────────────────────

    graph = StateGraph(AgentState)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", tool_node)
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
