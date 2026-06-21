"""
db.py — asyncpg connection-pool lifecycle + a per-request dependency.

Why a pool, not a connection per request: opening a Postgres connection is
expensive (TCP + auth + backend process). The pool keeps a set of warm
connections and hands them out, amortising that cost.

In Step 3 (vector retrieval) we'll register pgvector's type codec on each
pooled connection so `vector(1536)` round-trips as a Python list. The hook is
already wired below (`_init_connection`) but kept a no-op until then.
"""

from __future__ import annotations

import asyncpg
from fastapi import Request

from app.config import get_settings


async def _init_connection(conn: asyncpg.Connection) -> None:
    # Register pgvector's codec on every pooled connection so a Python list of
    # floats round-trips directly as a `vector(384)` — no manual string-encoding.
    # Needed from Step 2 (we now INSERT embeddings).
    from pgvector.asyncpg import register_vector

    await register_vector(conn)


async def create_pool() -> asyncpg.Pool:
    """Create the pool and fail fast if Postgres is unreachable."""
    s = get_settings()
    pool = await asyncpg.create_pool(
        dsn=s.database_url,
        min_size=s.pool_min_size,
        max_size=s.pool_max_size,
        command_timeout=s.command_timeout,
        init=_init_connection,
    )
    # Prove connectivity at startup rather than on the first request.
    async with pool.acquire() as conn:
        await conn.execute("SELECT 1")
    return pool


async def get_conn(request: Request) -> asyncpg.Connection:
    """FastAPI dependency: yield a pooled connection, always returned to the pool."""
    pool: asyncpg.Pool = request.app.state.pool
    async with pool.acquire() as conn:
        yield conn
