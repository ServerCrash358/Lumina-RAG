"""
main.py — composition root.

Step 1 wires up the skeleton: a lifespan that opens the asyncpg pool + Redis at
startup and closes them at shutdown, plus health routes. The RAG endpoints
(/ingest, /query), Prometheus middleware, embedder/retriever/reranker get added
in later steps — the structure here is what they'll plug into.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

import redis.asyncio as aredis
from fastapi import FastAPI
from fastapi.responses import ORJSONResponse

from app.config import get_settings
from app.db import create_pool
from app.routers import health, ingest, query, search


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    # Startup: create shared clients once, store on app.state.
    app.state.pool = await create_pool()
    app.state.redis = aredis.from_url(s.redis_url)
    try:
        yield
    finally:
        # Shutdown: release resources cleanly.
        await app.state.redis.aclose()
        await app.state.pool.close()


app = FastAPI(
    title="Lumina",
    summary="A production RAG API — answers grounded in your documents.",
    version="0.1.0",
    default_response_class=ORJSONResponse,
    lifespan=lifespan,
)

app.include_router(health.router)
app.include_router(ingest.router)
app.include_router(search.router)
app.include_router(query.router)


@app.get("/")
async def root() -> dict[str, str]:
    return {"name": "lumina", "status": "ok", "docs": "/docs"}
