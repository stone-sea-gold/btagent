"""CopilotKit runtime endpoint for Agent chat."""

from fastapi import APIRouter

from copilotkit import CopilotKitRemoteEndpoint, LangGraphAGUIAgent

from src.api.dependencies import get_services
from src.agent.graph import create_agent_graph

router = APIRouter()


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

    # Wrap in CopilotKit agent
    agent = LangGraphAGUIAgent(
        name="aifund5_agent",
        graph=graph,
        description="AIFUND5 量化投资助手 - 可以帮你选股、构建策略、运行回测",
    )

    # Create endpoint
    endpoint = CopilotKitRemoteEndpoint(actions=[], agents=[agent])
    return endpoint


# Lazy-initialized endpoint
copilotkit_endpoint = None


def get_copilotkit_endpoint():
    """Lazy initialize the CopilotKit endpoint."""
    global copilotkit_endpoint
    if copilotkit_endpoint is None:
        copilotkit_endpoint = create_copilotkit_endpoint()
    return copilotkit_endpoint
