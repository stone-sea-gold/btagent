"""Claude API client with timeout, retry, and exponential backoff.

Wraps the Anthropic SDK to provide:
- Configurable timeout (default 60s)
- Automatic retries with exponential backoff (default 3 attempts)
- Structured logging of every API call (latency, token usage, errors)
- Unified LLMError on failure
"""

import time

import anthropic

from src.config import settings
from src.exceptions import LLMError
from src.logging import get_logger

logger = get_logger("llm_client")


class LLMClient:
    """Resilient Claude API client."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
    ):
        self.api_key = api_key or settings.anthropic_api_key
        self.model = model or settings.anthropic_model
        self.timeout = timeout or settings.anthropic_timeout
        self.max_retries = max_retries or settings.anthropic_max_retries

        if not self.api_key:
            raise LLMError("ANTHROPIC_API_KEY not set. Check .env file.")

        self._client = anthropic.Anthropic(
            api_key=self.api_key,
            timeout=self.timeout,
        )

    def chat(
        self,
        messages: list[dict],
        system: str = "",
        tools: list[dict] | None = None,
        max_tokens: int = 4096,
    ) -> anthropic.types.Message:
        """Send a chat request with retry logic.

        Args:
            messages: Conversation messages.
            system: System prompt.
            tools: Tool definitions for tool use.
            max_tokens: Max response tokens.

        Returns:
            Anthropic Message object.

        Raises:
            LLMError: After all retries exhausted.
        """
        last_error = None

        for attempt in range(1, self.max_retries + 1):
            start = time.monotonic()
            try:
                kwargs = {
                    "model": self.model,
                    "max_tokens": max_tokens,
                    "messages": messages,
                }
                if system:
                    kwargs["system"] = system
                if tools:
                    kwargs["tools"] = tools

                response = self._client.messages.create(**kwargs)
                duration_ms = (time.monotonic() - start) * 1000

                logger.info(
                    "llm_call_success",
                    model=self.model,
                    attempt=attempt,
                    duration_ms=round(duration_ms, 1),
                    input_tokens=response.usage.input_tokens,
                    output_tokens=response.usage.output_tokens,
                    stop_reason=response.stop_reason,
                )
                return response

            except anthropic.APITimeoutError as e:
                duration_ms = (time.monotonic() - start) * 1000
                last_error = e
                logger.warning(
                    "llm_call_timeout",
                    attempt=attempt,
                    max_retries=self.max_retries,
                    duration_ms=round(duration_ms, 1),
                )

            except anthropic.RateLimitError as e:
                duration_ms = (time.monotonic() - start) * 1000
                last_error = e
                backoff = 2**attempt
                logger.warning(
                    "llm_rate_limited",
                    attempt=attempt,
                    backoff_seconds=backoff,
                    duration_ms=round(duration_ms, 1),
                )
                time.sleep(backoff)

            except anthropic.APIError as e:
                duration_ms = (time.monotonic() - start) * 1000
                last_error = e
                logger.warning(
                    "llm_api_error",
                    attempt=attempt,
                    error_type=type(e).__name__,
                    error_message=str(e),
                    duration_ms=round(duration_ms, 1),
                )
                if attempt < self.max_retries:
                    backoff = 2**attempt
                    time.sleep(backoff)

        raise LLMError(
            f"Claude API failed after {self.max_retries} attempts: {last_error}",
            details={"last_error": str(last_error), "attempts": self.max_retries},
        )
