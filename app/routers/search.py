"""
search.py — POST /search: stage-1 vector retrieval (no rerank/LLM yet).

Flow: embed the query with the SAME local model used at ingest (bge wants its
instruction prefix on queries — handled in embed_query) → ANN search over HNSW →
return the top-K chunks ranked by cosine similarity.

This endpoint exposes raw retrieval so you can see what the vector index returns
before reranking. In Step 4 a /query endpoint will wrap this with the
cross-encoder reranker + LLM generation.
"""

from __future__ import annotations

import asyncio
import json

import asyncpg
from fastapi import APIRouter, Depends

from app.config import get_settings
from app.db import get_conn
from app.schemas import SearchHit, SearchRequest, SearchResponse
from app.services.embedder import embed_query
from app.services.retriever import retrieve

router = APIRouter(tags=["search"])


@router.post("/search", response_model=SearchResponse)
async def search(req: SearchRequest, conn: asyncpg.Connection = Depends(get_conn)) -> SearchResponse:
    s = get_settings()
    top_k = req.top_k or s.top_k_retrieve

    # Embedding is blocking → run in a thread so the event loop stays free.
    query_vec = await asyncio.to_thread(embed_query, req.query)
    rows = await retrieve(conn, query_vec, top_k, s.hnsw_ef_search)

    results = [
        SearchHit(
            id=str(r["id"]),
            content=r["content"],
            # asyncpg returns jsonb as a JSON string by default; parse it back.
            metadata=json.loads(r["metadata"]) if isinstance(r["metadata"], str) else r["metadata"],
            score=round(float(r["score"]), 4),
        )
        for r in rows
    ]
    return SearchResponse(query=req.query, count=len(results), results=results)
