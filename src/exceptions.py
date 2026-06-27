"""Unified exception hierarchy for AIFUND5.

All custom exceptions inherit from AIFundError. The top-level exception
handler in cli.py / api catches AIFundError and returns a user-friendly
message while logging the full traceback via structlog.
"""


class AIFundError(Exception):
    """Base exception for all AIFUND5 errors."""

    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class FactorError(AIFundError):
    """Errors related to factor operations."""


class FactorNotFoundError(FactorError):
    """Requested factor does not exist in the registry."""


class FactorDuplicateError(FactorError):
    """Factor with the same name already exists."""


class FactorValidationError(FactorError):
    """Factor definition is invalid."""


class StrategyError(AIFundError):
    """Errors related to strategy operations."""


class StrategyCompileError(StrategyError):
    """Failed to compile a strategy config into a Qlib strategy."""


class StrategyNotFoundError(StrategyError):
    """Requested strategy does not exist."""


class BacktestError(AIFundError):
    """Errors related to backtest execution."""


class BacktestTimeoutError(BacktestError):
    """Backtest execution timed out."""


class AgentError(AIFundError):
    """Errors related to agent orchestration."""


class LLMError(AgentError):
    """LLM API call failed after retries."""


class ToolExecutionError(AgentError):
    """Agent tool execution failed."""


class SessionError(AIFundError):
    """Errors related to session management."""


class SessionNotFoundError(SessionError):
    """Requested session does not exist."""
