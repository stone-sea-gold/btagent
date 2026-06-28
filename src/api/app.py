"""FastAPI application — AIFUND5 API server.

Usage:
    uvicorn src.api.app:app --reload --port 8000
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.dependencies import close_services, init_services
from src.api.middleware import setup_error_handlers, setup_request_logging
from src.logging import configure_logging, get_logger

logger = get_logger("api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan — initialize and cleanup services."""
    configure_logging("INFO")
    logger.info("api_startup")
    services = init_services()
    logger.info("api_services_initialized", factors=len(services.factor_store.list_all()))
    yield
    logger.info("api_shutdown")
    close_services()


app = FastAPI(
    title="AIFUND5 API",
    description="A股量化投资助手 API",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:5174", "http://localhost:5175", "http://127.0.0.1:5173", "http://127.0.0.1:5174", "http://127.0.0.1:5175"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

setup_error_handlers(app)
setup_request_logging(app)


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok", "version": "0.1.0"}


# Register REST route modules
from src.api.routes import backtest, calendar, data, factors, portfolio, selection, strategies  # noqa: E402

app.include_router(factors.router, prefix="/api/factors", tags=["factors"])
app.include_router(strategies.router, prefix="/api/strategies", tags=["strategies"])
app.include_router(backtest.router, prefix="/api/backtest", tags=["backtest"])
app.include_router(selection.router, prefix="/api/selection", tags=["selection"])
app.include_router(portfolio.router, prefix="/api/portfolio", tags=["portfolio"])
app.include_router(calendar.router, prefix="/api/calendar", tags=["calendar"])
app.include_router(data.router, prefix="/api/data", tags=["data"])


# Register CopilotKit AG-UI endpoint
from fastapi import Request  # noqa: E402
from copilotkit.integrations.fastapi import handler as _copilotkit_handler  # noqa: E402
from src.api.routes.chat import get_copilotkit_endpoint  # noqa: E402


# Handle bare /api/chat (info endpoint) and /api/chat/agent/name (execution)
@app.api_route("/api/chat", methods=["GET", "POST", "OPTIONS"])
@app.api_route("/api/chat/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])
async def copilotkit_chat(request: Request, path: str = ""):
    """CopilotKit AG-UI endpoint."""
    request.path_params["path"] = path
    return await _copilotkit_handler(request, get_copilotkit_endpoint())
