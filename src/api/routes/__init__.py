"""API route modules.

Handlers here are declared ``def`` rather than ``async def`` on purpose. The
business layer — qlib backtests, DuckDB reads, ChromaDB lookups, outbound HTTP
fetches — is synchronous, so an ``async def`` handler would run that work
directly on the event loop and freeze every other request for its whole
duration, including an in-flight SSE chat stream. FastAPI runs ``def`` handlers
in a threadpool, which keeps the loop free.

``chat_sse`` is the deliberate exception: it is genuinely async (it awaits the
request body and streams from the graph), so it stays ``async def``.
"""
