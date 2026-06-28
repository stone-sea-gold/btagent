"""CopilotKit runtime endpoint for Agent chat.

LangGraphAgentAdapter bridges the gap between CopilotKit's Agent ABC
(which requires execute()) and LangGraphAGUIAgent (which doesn't inherit from it).
"""

import uuid
from typing import Optional

from fastapi import APIRouter

from copilotkit import CopilotKitRemoteEndpoint
from copilotkit.langgraph_agui_agent import LangGraphAGUIAgent
from copilotkit.agent import Agent
from copilotkit.types import Message
from copilotkit.action import ActionDict
from copilotkit.types import MetaEvent
from ag_ui.core.types import RunAgentInput

from src.api.dependencies import get_services
from src.agent.graph import create_agent_graph


class LangGraphAgentAdapter(Agent):
    """Adapter: wraps LangGraphAGUIAgent to satisfy CopilotKit's Agent ABC."""

    def __init__(self, *, name: str, graph, description: Optional[str] = None):
        self._inner = LangGraphAGUIAgent(
            name=name, graph=graph, description=description
        )
        self._name = name
        self._description = description

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str | None:
        return self._description

    def execute(  # type: ignore[override]
        self,
        *,
        state: dict,
        config: Optional[dict] = None,
        messages: list[Message],
        thread_id: str,
        actions: Optional[list[ActionDict]] = None,
        meta_events: Optional[list[MetaEvent]] = None,
        **kwargs,
    ):
        """Bridging execute — delegates to LangGraphAgent.run()."""
        input_data = RunAgentInput(
            thread_id=thread_id,
            run_id=str(uuid.uuid4()),
            state=state,
            messages=messages,
            tools=[],
            context=[],
            forwarded_props={"node_name": kwargs.get("node_name")},
        )
        return self._inner.run(input_data)

    async def get_state(self, *, thread_id: str):
        return await self._inner.get_state(thread_id=thread_id)

    def dict_repr(self):
        return {
            "name": self.name,
            "description": self.description or "",
            "type": "langgraph_agui",
        }


def create_copilotkit_endpoint():
    """Create the CopilotKit endpoint with the agent graph."""
    services = get_services()

    # Create the agent graph
    graph = create_agent_graph(
        factor_store=services.factor_store,
        strategy_compiler=services.strategy_compiler,
        backtest_engine=services.backtest_engine,
        strategy_store=services.strategy_store,
        session_store=services.session_store,
        position_manager=services.position_manager,
        param_optimizer=services.param_optimizer,
        stock_selector=services.stock_selector,
    )

    # Wrap in CopilotKit-compatible adapter
    agent = LangGraphAgentAdapter(
        name="default",
        graph=graph,
        description="AIFUND5 量化投资助手 - 可以帮你选股、构建策略、运行回测",
    )

    # Custom endpoint that returns agents as name-keyed object (not array)
    # so the CopilotKit JS client can index them by name.
    class _CustomEndpoint(CopilotKitRemoteEndpoint):
        def info(self, *, context):
            result = super().info(context=context)
            # Convert agents list to name-keyed dict for the JS client
            result["agents"] = {a["name"]: a for a in result["agents"]}
            return result

    endpoint = _CustomEndpoint(actions=[], agents=[agent])
    return endpoint


# Lazy-initialized endpoint
copilotkit_endpoint = None


def get_copilotkit_endpoint():
    """Lazy initialize the CopilotKit endpoint."""
    global copilotkit_endpoint
    if copilotkit_endpoint is None:
        copilotkit_endpoint = create_copilotkit_endpoint()
    return copilotkit_endpoint
