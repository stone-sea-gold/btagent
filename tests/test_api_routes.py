"""Regression guard on the API's concurrency shape.

Handlers that call the synchronous business layer must stay ``def``: FastAPI
runs those in a threadpool, whereas an ``async def`` handler executes the same
blocking work directly on the event loop and stalls every other request for its
duration. The rule is documented in :mod:`src.api.routes` and is easy to undo by
accident, so it is pinned here.
"""

import inspect

from fastapi.routing import APIRoute

from src.api.app import app

# Genuinely async: the SSE endpoint awaits the request body and streams from the
# graph; /health returns a literal and never blocks.
ASYNC_HANDLERS = {"chat_sse", "health"}


def _iter_api_routes(routes, prefix=""):
    """Yield ``(path, route)`` for every APIRoute, descending into routers.

    FastAPI keeps included routers wrapped rather than flattening them into
    ``app.routes``, so the real routes are reached through the wrapper.
    """
    for route in routes:
        if isinstance(route, APIRoute):
            yield prefix + route.path, route
            continue
        for attribute in ("original_router", "router", "routes", "app"):
            holder = getattr(route, attribute, None)
            subroutes = getattr(holder, "routes", None)
            if subroutes:
                yield from _iter_api_routes(
                    subroutes, prefix + getattr(route, "prefix", "")
                )


def _api_routes() -> list[tuple[str, APIRoute]]:
    return list(_iter_api_routes(app.routes))


class TestHandlerConcurrency:
    def test_the_walk_finds_the_real_surface(self):
        """Guard against a vacuous pass if the router layout changes."""
        assert len(_api_routes()) > 30

    def test_blocking_handlers_are_sync(self):
        offenders = [
            f"{path} ({route.endpoint.__name__})"
            for path, route in _api_routes()
            if route.endpoint.__name__ not in ASYNC_HANDLERS
            and inspect.iscoroutinefunction(route.endpoint)
        ]
        assert offenders == [], (
            "these handlers call the sync business layer and must be 'def' so "
            f"FastAPI runs them in a threadpool: {offenders}"
        )

    def test_sse_endpoint_is_async(self):
        by_name = {r.endpoint.__name__: r for _, r in _api_routes()}
        assert "chat_sse" in by_name
        assert inspect.iscoroutinefunction(by_name["chat_sse"].endpoint)
