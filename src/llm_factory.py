"""LLM factory — auto-detects API protocol from URL.

Protocol detection logic:
1. If base_url contains "/anthropic" → Anthropic protocol (ChatAnthropic)
2. Otherwise → OpenAI protocol (ChatOpenAI)
3. "ollama" → ChatOllama (always)
4. Official "anthropic" provider (no custom URL) → ChatAnthropic with official endpoint
5. Official "openai" provider (no custom URL) → ChatOpenAI with official endpoint

This means ANY provider that offers OpenAI or Anthropic-compatible APIs
can be used by just setting the URL correctly.
"""

from langchain_core.language_models import BaseChatModel

from src.config import settings
from src.exceptions import LLMError
from src.logging import get_logger

logger = get_logger("llm_factory")


def _detect_protocol(base_url: str) -> str:
    """Detect API protocol from URL.

    Detection rules:
    1. URL contains "/anthropic" (path) → Anthropic protocol
    2. Domain contains "anthropic" (e.g., api.anthropic.com) → Anthropic protocol
    3. Otherwise → OpenAI protocol (default)

    Returns:
        "anthropic" or "openai"
    """
    if not base_url:
        return "openai"
    url_lower = base_url.lower()
    # Check for "/anthropic" in path (e.g., api.deepseek.com/anthropic)
    if "/anthropic" in url_lower:
        return "anthropic"
    # Check for "anthropic" in domain (e.g., api.anthropic.com)
    if "anthropic" in url_lower.split("//")[-1].split("/")[0]:
        return "anthropic"
    return "openai"


def _create_chat_anthropic(api_key: str, model: str, base_url: str = "") -> BaseChatModel:
    """Create ChatAnthropic instance."""
    from langchain_anthropic import ChatAnthropic

    kwargs = {
        "model": model,
        "anthropic_api_key": api_key,
        "timeout": settings.llm_timeout,
        "max_retries": settings.llm_max_retries,
    }
    if base_url:
        kwargs["base_url"] = base_url
    return ChatAnthropic(**kwargs)


def _create_chat_openai(api_key: str, model: str, base_url: str = "") -> BaseChatModel:
    """Create ChatOpenAI instance."""
    from langchain_openai import ChatOpenAI

    kwargs = {
        "model": model,
        "api_key": api_key,
        "timeout": settings.llm_timeout,
        "max_retries": settings.llm_max_retries,
    }
    if base_url:
        kwargs["base_url"] = base_url
    return ChatOpenAI(**kwargs)


def create_llm() -> BaseChatModel:
    """Create a LangChain chat model based on settings.

    Auto-detects protocol from URL for maximum flexibility.
    """
    provider = settings.llm_provider.lower()
    logger.info("creating_llm", provider=provider)

    # ── Anthropic (official) ───────────────────────────────────────
    if provider == "anthropic":
        if not settings.anthropic_api_key:
            raise LLMError("ANTHROPIC_API_KEY not set. Check .env file.")
        return _create_chat_anthropic(
            api_key=settings.anthropic_api_key,
            model=settings.anthropic_model,
        )

    # ── OpenAI (official) ─────────────────────────────────────────
    if provider == "openai":
        if not settings.openai_api_key:
            raise LLMError("OPENAI_API_KEY not set. Check .env file.")
        return _create_chat_openai(
            api_key=settings.openai_api_key,
            model=settings.openai_model,
            base_url=settings.openai_base_url,
        )

    # ── DeepSeek ──────────────────────────────────────────────────
    if provider == "deepseek":
        if not settings.deepseek_api_key:
            raise LLMError("DEEPSEEK_API_KEY not set. Check .env file.")
        protocol = _detect_protocol(settings.deepseek_base_url)
        logger.info("deepseek_protocol_detected", protocol=protocol, url=settings.deepseek_base_url)
        if protocol == "anthropic":
            return _create_chat_anthropic(
                api_key=settings.deepseek_api_key,
                model=settings.deepseek_model,
                base_url=settings.deepseek_base_url,
            )
        else:
            return _create_chat_openai(
                api_key=settings.deepseek_api_key,
                model=settings.deepseek_model,
                base_url=settings.deepseek_base_url,
            )

    # ── Ollama (local) ────────────────────────────────────────────
    if provider == "ollama":
        from langchain_ollama import ChatOllama
        return ChatOllama(
            model=settings.ollama_model,
            base_url=settings.ollama_base_url,
            timeout=settings.llm_timeout,
        )

    # ── Custom (auto-detect protocol from URL) ────────────────────
    if provider == "custom":
        if not settings.llm_api_key:
            raise LLMError("LLM_API_KEY not set for custom provider. Check .env file.")
        if not settings.llm_model:
            raise LLMError("LLM_MODEL not set for custom provider. Check .env file.")
        if not settings.llm_base_url:
            raise LLMError("LLM_BASE_URL not set for custom provider. Check .env file.")

        protocol = _detect_protocol(settings.llm_base_url)
        logger.info("custom_protocol_detected", protocol=protocol, url=settings.llm_base_url)
        if protocol == "anthropic":
            return _create_chat_anthropic(
                api_key=settings.llm_api_key,
                model=settings.llm_model,
                base_url=settings.llm_base_url,
            )
        else:
            return _create_chat_openai(
                api_key=settings.llm_api_key,
                model=settings.llm_model,
                base_url=settings.llm_base_url,
            )

    raise LLMError(
        f"Unsupported LLM provider: '{provider}'",
        details={"supported": ["anthropic", "openai", "deepseek", "ollama", "custom"]},
    )
