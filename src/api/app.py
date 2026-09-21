"""FastAPI application — AIFUND5 API server.

Usage:
    uvicorn src.api.app:app --reload --port 8000
"""

from contextlib import asynccontextmanager
from datetime import date
from threading import Thread

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.dependencies import close_services, init_services
from src.api.middleware import setup_error_handlers, setup_request_logging
from src.data.providers import close_providers, get_provider
from src.logging import configure_logging, get_logger

logger = get_logger("api")


def _warm_provider_session() -> None:
    """Log in to the primary data source in the background.

    BaoStock's login measured 75-78s here, so paying it at startup means the
    first sync a user starts does not have to. A failure is only logged: warming
    is an optimisation, and the sync path retries the login on its own.
    """
    # Imported here because the route module below is also named ``settings``.
    from src.config import settings

    name = settings.data_source_priority.split(",")[0].strip()
    try:
        today = date.today()  # noqa: DTZ011 - a trading window, not an instant
        get_provider(name).get_calendar(today, today)
        logger.info("provider_warmup_done", source=name)
    except Exception as exc:  # noqa: BLE001 - warm-up must never break startup
        logger.warning("provider_warmup_failed", source=name, error=str(exc))


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan — initialize and cleanup services."""
    configure_logging("INFO")
    logger.info("api_startup")
    services = init_services()
    logger.info("api_services_initialized", factors=len(services.factor_store.list_all()))
    # Daemon thread: startup must not block for the login it is hiding.
    Thread(target=_warm_provider_session, name="provider-warmup", daemon=True).start()
    yield
    logger.info("api_shutdown")
    close_providers()
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
from src.api.routes import backtest, calendar, chats, data, factors, market_data, portfolio, selection, settings, strategies  # noqa: E402

app.include_router(chats.router, prefix="/api/chats", tags=["chats"])
app.include_router(factors.router, prefix="/api/factors", tags=["factors"])
app.include_router(strategies.router, prefix="/api/strategies", tags=["strategies"])
app.include_router(backtest.router, prefix="/api/backtest", tags=["backtest"])
app.include_router(selection.router, prefix="/api/selection", tags=["selection"])
app.include_router(portfolio.router, prefix="/api/portfolio", tags=["portfolio"])
app.include_router(calendar.router, prefix="/api/calendar", tags=["calendar"])
app.include_router(data.router, prefix="/api/data", tags=["data"])
app.include_router(settings.router, prefix="/api/settings", tags=["settings"])
app.include_router(market_data.router, prefix="/api/market-data", tags=["market-data"])


# Register Vercel AI SDK chat SSE endpoint
from src.api.routes.chat_sse import router as chat_sse_router  # noqa: E402

app.include_router(chat_sse_router, tags=["chat"])
