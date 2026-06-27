"""API middleware — CORS, error handling, request logging."""

import time
import traceback

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.config import settings
from src.exceptions import AIFundError
from src.logging import get_logger

logger = get_logger("api")


def setup_cors(app: FastAPI, origins: list[str] | None = None):
    """Configure CORS middleware."""
    allowed_origins = origins or [
        "http://localhost:5173",  # Vite dev server
        "http://localhost:3000",  # Alternative dev port
        "http://127.0.0.1:5173",
    ]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


def setup_error_handlers(app: FastAPI):
    """Configure global error handlers."""

    @app.exception_handler(AIFundError)
    async def aifund_error_handler(request: Request, exc: AIFundError):
        logger.error(
            "api_error",
            path=request.url.path,
            error=exc.message,
            details=exc.details,
        )
        return JSONResponse(
            status_code=400,
            content={
                "error": exc.message,
                "details": exc.details,
                "type": type(exc).__name__,
            },
        )

    @app.exception_handler(Exception)
    async def generic_error_handler(request: Request, exc: Exception):
        logger.error(
            "unexpected_error",
            path=request.url.path,
            error=str(exc),
            traceback=traceback.format_exc(),
        )
        return JSONResponse(
            status_code=500,
            content={
                "error": "服务器内部错误，请稍后重试",
                "type": "InternalServerError",
            },
        )


def setup_request_logging(app: FastAPI):
    """Add request timing middleware."""

    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        start = time.monotonic()
        response = await call_next(request)
        duration_ms = (time.monotonic() - start) * 1000

        logger.info(
            "api_request",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            duration_ms=round(duration_ms, 1),
        )
        return response
