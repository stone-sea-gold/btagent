"""Agent session state for LangGraph."""

import operator
from typing import Annotated, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    """State for the AIFUND5 agent graph.

    This is the mutable state that flows through the LangGraph nodes.

    ``messages`` and ``tool_call_log`` carry reducers, so node updates append.
    The two context fields hold the latest value: they describe what the agent
    is currently working on, so overwriting is the intended semantics.
    """

    messages: Annotated[list[BaseMessage], add_messages]
    """Full conversation, including tool calls and tool results."""

    session_id: str
    """Identifier of the owning session."""

    current_strategy: dict | None
    """Most recent strategy config composed successfully."""

    last_backtest_result: dict | None
    """Most recent backtest result produced successfully."""

    tool_call_log: Annotated[list[dict], operator.add]
    """Append-only record of every tool call: name, outcome, duration."""
