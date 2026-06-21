"""
retriever.py — stage-1 retrieval: approximate nearest-neighbour search in pgvector.

Given a query embedding, find the most similar document chunks. This is the
"cast a wide net" stage: fast, high-recall, returns ~top-20 candidates that a
cross-encoder will then re-rank for precision in Step 4.

The `<=>` operator is pgvector's COSINE DISTANCE (0 = identical, 2 = opposite),
because our HNSW index was built with vector_cosine_ops. Cosine *similarity* is
just `1 - distance`, which we return as the score (1.0 = perfect match).

ORDER BY embedding <=> $1 is what lets Postgres use the HNSW index — it walks
the proximity graph instead of scanning every row, so search stays fast as the
corpus grows from thousands to millions of chunks.
"""

from __future__ import annotations

import asyncpg


async def retrieve(
    conn: asyncpg.Connection,
    query_vec: list[float],
    top_k: int,
    ef_search: int,
) -> list[asyncpg.Record]:
    # SET LOCAL keeps the ef_search tuning scoped to THIS transaction, so it
    # doesn't leak onto other requests sharing the pooled connection.
    async with conn.transaction():
        await conn.execute(f"SET LOCAL hnsw.ef_search = {int(ef_search)}")
        return await conn.fetch(
            """
            SELECT id, content, metadata,
                   1 - (embedding <=> $1) AS score
            FROM documents
            WHERE embedding IS NOT NULL
            ORDER BY embedding <=> $1
            LIMIT $2
            """,
            query_vec,
            top_k,
        )
