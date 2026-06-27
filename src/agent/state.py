"""Agent session state for LangGraph."""

from typing import Annotated, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    """State for the AIFUND5 agent graph.

    This is the mutable state that flows through the LangGraph nodes.
    """
    messages: Annotated[list[BaseMessage], add_messages]
    session_id: str
    current_strategy: dict | None
    last_backtest_result: dict | None
    tool_call_log: list[dict]
