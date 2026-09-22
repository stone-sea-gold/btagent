"""Probe an LLM configuration without saving it.

Saving a preset used to prove nothing. ``create_llm()`` builds the client
locally and never sends a request, so a wrong key, a wrong model name, or a
gateway that demands an extra header all surfaced only once the user sent a
chat message — and then as a raw provider error. This runs one small, real,
streaming, tool-bound call so the settings page can answer "does this actually
work?" before the config is stored.

Binding a tool is deliberate. The agent drives 57 tools, so a provider that
answers plain chat but mishandles tool calls is not usable here even though a
naive reachability check would pass it. The probe therefore reports
``tool_calling`` separately from ``ok``.
"""

import re
import time
from typing import Any

from src.core.models import LLMConfig
from src.llm_factory import create_llm
from src.logging import get_logger

logger = get_logger("llm_probe")

#: One trivial tool, so the probe exercises what the agent actually needs.
PROBE_TOOL = {
    "type": "function",
    "function": {
        "name": "get_latest_price",
        "description": "查询一只股票的最新价格",
        "parameters": {
            "type": "object",
            "properties": {"code": {"type": "string", "description": "股票代码"}},
            "required": ["code"],
        },
    },
}

PROBE_PROMPT = "请调用工具查询 600519 的最新价格。"

#: Where the failure happened, with the action that fixes it.
_STAGE_HINT = {
    "config": "配置不完整，请先补齐标出的字段。",
    "connect": "无法建立连接：请检查 Base URL 是否正确、网络是否可达。",
    "auth": "API Key 无效或未授权（401/403）。",
    "quota": "API 额度不足，请检查账户余额（402）。",
    "model": "端点或模型名不存在（404），请检查 Base URL 与 Model。",
    "request": "请求被拒绝（400）：模型名可能不被该端点支持，或该网关要求额外的请求头/参数。",
    "rate_limit": "请求频率过高（429），请稍后重试。",
    "timeout": "请求超时，请检查网络或 Base URL。",
    "stream": "连接成功但流式响应中断，该端点可能不支持流式输出。",
    "ok": "",
}

_STATUS_STAGE = {
    400: "request",
    401: "auth",
    402: "quota",
    403: "auth",
    404: "model",
    429: "rate_limit",
}

_SAMPLE_LIMIT = 200
_DETAIL_LIMIT = 400


def _status_of(exc: Exception) -> int | None:
    """HTTP status of ``exc``, if it carries one.

    Both SDKs expose ``status_code`` on their errors, but LangChain sometimes
    wraps them, and the wrapped message still spells the code out as
    ``Error code: 400`` — hence the text fallback.
    """
    for attr in ("status_code", "http_status", "code"):
        value = getattr(exc, attr, None)
        if isinstance(value, int) and 100 <= value <= 599:
            return value
    response = getattr(exc, "response", None)
    value = getattr(response, "status_code", None)
    if isinstance(value, int) and 100 <= value <= 599:
        return value
    match = re.search(r"Error code:\s*(\d{3})", str(exc))
    return int(match.group(1)) if match else None


def _stage_of(exc: Exception) -> str:
    """Coarse failure stage, so the UI can name the step that broke."""
    status = _status_of(exc)
    if status in _STATUS_STAGE:
        return _STATUS_STAGE[status]
    if status is not None and 500 <= status <= 599:
        return "connect"
    name = type(exc).__name__.lower()
    if "timeout" in name:
        return "timeout"
    if "connect" in name or "connection" in name:
        return "connect"
    return "connect"


def _text_of(content: Any) -> str:
    """Flatten a message's content, which may be a string or content blocks."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                parts.append(str(block.get("text", "")))
            else:
                parts.append(str(block))
        return "".join(parts)
    return str(content or "")


def probe_llm_config(cfg: LLMConfig) -> dict:
    """Run one real tool-bound streaming call and report where it landed.

    Never raises: a probe that throws is useless to the caller, which wants a
    verdict to render. ``ok`` is true only when the endpoint answered; a
    response that carried no tool call is still ``ok`` but says so through
    ``tool_calling``.
    """
    result: dict[str, Any] = {
        "ok": False,
        "stage": "config",
        "hint": "",
        "http_status": None,
        "latency_ms": 0,
        "ttft_ms": None,
        "tool_calling": False,
        "tool_names": [],
        "sample": "",
        "detail": "",
    }

    # create_llm() falls back to .env when any of these is empty. Without this
    # guard an incomplete form would probe the .env config and report success.
    missing = [
        name
        for name, value in (
            ("Base URL", cfg.base_url),
            ("API Key", cfg.api_key),
            ("Model", cfg.model),
        )
        if not value.strip()
    ]
    if missing:
        result["hint"] = f"配置不完整，请先填写：{'、'.join(missing)}"
        return result

    started = time.monotonic()
    try:
        llm = create_llm(cfg).bind_tools([PROBE_TOOL])
    except Exception as exc:  # noqa: BLE001 — reported, not swallowed
        result["latency_ms"] = round((time.monotonic() - started) * 1000)
        result["detail"] = str(exc)[:_DETAIL_LIMIT]
        result["hint"] = f"无法按当前配置创建客户端：{result['detail']}"
        return result

    try:
        stream = llm.stream(PROBE_PROMPT)
        first = next(stream)
        result["ttft_ms"] = round((time.monotonic() - started) * 1000)
        full = first
        for chunk in stream:
            full = full + chunk
    except StopIteration:
        result["latency_ms"] = round((time.monotonic() - started) * 1000)
        result["stage"] = "stream"
        result["hint"] = _STAGE_HINT["stream"]
        return result
    except Exception as exc:  # noqa: BLE001 — reported, not swallowed
        result["latency_ms"] = round((time.monotonic() - started) * 1000)
        result["stage"] = _stage_of(exc)
        result["http_status"] = _status_of(exc)
        result["detail"] = str(exc)[:_DETAIL_LIMIT]
        result["hint"] = _STAGE_HINT[result["stage"]]
        logger.info(
            "llm_probe_failed",
            stage=result["stage"],
            http_status=result["http_status"],
            model=cfg.model,
        )
        return result

    tool_names = [call.get("name", "") for call in (getattr(full, "tool_calls", None) or [])]
    result.update(
        ok=True,
        stage="ok",
        hint="",
        latency_ms=round((time.monotonic() - started) * 1000),
        tool_calling=bool(tool_names),
        tool_names=tool_names,
        sample=_text_of(getattr(full, "content", ""))[:_SAMPLE_LIMIT],
    )
    logger.info(
        "llm_probe_ok",
        model=cfg.model,
        latency_ms=result["latency_ms"],
        tool_calling=result["tool_calling"],
    )
    return result
