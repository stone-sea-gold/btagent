"""SSE chat endpoint for Vercel AI SDK useChat().

Receives messages in Vercel AI SDK format, runs the LangGraph agent,
and streams back events in the Vercel AI Data Stream protocol.
"""

import json
import logging
import uuid

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from src.agent.graph import create_agent_graph
from src.api.dependencies import get_services

logger = logging.getLogger("aifund5.chat_sse")

router = APIRouter()

# Lazy-initialized graph (no checkpointer — stateless, useChat carries history)
_graph = None


def _get_graph():
    global _graph
    if _graph is None:
        services = get_services()
        _graph = create_agent_graph(
            factor_store=services.factor_store,
            strategy_compiler=services.strategy_compiler,
            backtest_engine=services.backtest_engine,
            strategy_store=services.strategy_store,
            session_store=services.session_store,
            position_manager=services.position_manager,
            param_optimizer=services.param_optimizer,
            stock_selector=services.stock_selector,
            checkpointer=None,
        )
    return _graph


def _convert_messages(ai_messages: list[dict]) -> list:
    """Convert Vercel AI SDK messages to LangChain messages."""
    lc_messages = []
    for msg in ai_messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")

        if role == "user":
            lc_messages.append(HumanMessage(content=content))

        elif role == "assistant":
            tool_invocations = msg.get("toolInvocations", [])
            if tool_invocations:
                # Assistant message with tool calls
                tool_calls = []
                for inv in tool_invocations:
                    tool_calls.append({
                        "id": inv.get("toolCallId", str(uuid.uuid4())),
                        "name": inv.get("toolName", ""),
                        "args": inv.get("args", {}),
                    })
                lc_messages.append(AIMessage(content=content or "", tool_calls=tool_calls))

                # Tool results as ToolMessage
                for inv in tool_invocations:
                    if inv.get("state") == "result":
                        result = inv.get("result", "")
                        if not isinstance(result, str):
                            result = json.dumps(result, ensure_ascii=False)
                        lc_messages.append(ToolMessage(
                            content=result,
                            tool_call_id=inv.get("toolCallId", ""),
                        ))
            else:
                lc_messages.append(AIMessage(content=content))

        # Skip "tool" role messages (folded into toolInvocations above)

    return lc_messages


@router.post("/api/chat")
async def chat_sse(request: Request):
    """SSE endpoint compatible with Vercel AI SDK useChat()."""
    try:
        body = await request.json()
    except Exception:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=400, content={"error": "Invalid JSON"})
    messages = body.get("messages", [])

    lc_messages = _convert_messages(messages)

    graph = _get_graph()

    async def event_stream():
        try:
            input_state = {
                "messages": lc_messages,
                "session_id": "",
                "current_strategy": None,
                "last_backtest_result": None,
                "tool_call_log": [],
            }

            # Stream text from all LLM calls (skip tool call events for v4 compatibility)
            async for event in graph.astream_events(input_state, version="v2"):
                kind = event.get("event", "")

                if kind == "on_chat_model_stream":
                    chunk = event.get("data", {}).get("chunk")
                    if chunk and hasattr(chunk, "content") and chunk.content is not None:
                        content = chunk.content
                        if isinstance(content, list):
                            for block in content:
                                if isinstance(block, dict) and block.get("type") == "text":
                                    t = block.get("text", "")
                                    if t:
                                        yield f'0:{json.dumps(t, ensure_ascii=False)}\n'
                        elif isinstance(content, str) and content:
                            yield f"0:{json.dumps(content, ensure_ascii=False)}\n"

            yield 'e:{"finishReason":"stop"}\n'

        except Exception as exc:
            logger.exception("chat_sse_error")
            yield f'3:{json.dumps(str(exc))}\n'

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Vercel-AI-Data-Stream": "v1",
        },
    )
