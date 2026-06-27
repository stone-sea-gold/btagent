"""Structured logging configuration using structlog.

All logs are output as JSON with a consistent schema:
{
    "timestamp": "...",
    "level": "info",
    "event": "description",
    "session_id": "uuid",
    "tool_name": "search_factors",  // for tool calls
    "duration_ms": 123,             // for tool calls
    ...
}
"""

import logging
import uuid

import structlog

_session_id: str = ""


def get_session_id() -> str:
    """Return the current session's trace ID."""
    return _session_id


def new_session_id() -> str:
    """Generate and return a new session trace ID."""
    global _session_id
    _session_id = uuid.uuid4().hex[:12]
    return _session_id


def configure_logging(log_level: str = "INFO") -> None:
    """Configure structlog with JSON output and session context."""
    level = getattr(logging, log_level.upper(), logging.INFO)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.dev.set_exc_info,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.BoundLogger:
    """Return a bound logger with session context."""
    return structlog.get_logger(name).bind(session_id=get_session_id())
