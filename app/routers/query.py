"""
query.py — POST /query: the full RAG pipeline.

    cache check (Redis)  ── HIT ─→ return cached answer
        │ MISS
        ▼
    embed query  →  pgvector ANN (top-20)  →  cross-encoder rerank (top-5)
        →  LLM generate (grounded in top-5)  →  cache  →  answer + sources

This is the endpoint the capstone is really about — everything before it
(ingest, search, rerank, generate) exists to make this one call good.
"""

from __future__ import annotations

import asyncio
import hashlib
import json

import asyncpg
from fastapi import APIRouter, Depends, Request

from app.config import get_settings
from app.db import get_conn
from app.metrics import RAG_CACHE_HITS, RAG_CACHE_MISSES, track_stage
from app.schemas import QueryRequest, QueryResponse, Source
from app.services.embedder import embed_query
from app.services.generator import generate
from app.services.reranker import rerank
from app.services.retriever import retrieve

router = APIRouter(tags=["query"])


def _cache_key(question: str) -> str:
    return "rag:" + hashlib.sha256(question.encode()).hexdigest()


@router.post("/query", response_model=QueryResponse)
async def query(
    req: QueryRequest,
    request: Request,
    conn: asyncpg.Connection = Depends(get_conn),
) -> QueryResponse:
    s = get_settings()
    redis = request.app.state.redis
    key = _cache_key(req.question)

    # 1. Cache check — repeated questions skip the whole (expensive) pipeline.
    if s.cache_enabled:
        try:
            if cached := await redis.get(key):
                RAG_CACHE_HITS.inc()
                payload = json.loads(cached)
                return QueryResponse(**payload, cached=True)
        except Exception:
            pass  # cache is best-effort; never fail a query because Redis is down
    RAG_CACHE_MISSES.inc()

    # 2. Retrieve (stage 1): embed query → ANN over HNSW → top-20 candidates.
    with track_stage("embed"):
        query_vec = await asyncio.to_thread(embed_query, req.question)
    with track_stage("retrieve"):
        rows = await retrieve(conn, query_vec, s.top_k_retrieve, s.hnsw_ef_search)
    candidates = [
        {
            "content": r["content"],
            "metadata": json.loads(r["metadata"]) if isinstance(r["metadata"], str) else r["metadata"],
        }
        for r in rows
    ]

    if not candidates:
        return QueryResponse(question=req.question, answer="I don't know — no documents are indexed yet.", sources=[])

    # 3. Rerank (stage 2): cross-encoder picks the top-5 most relevant.
    with track_stage("rerank"):
        top = await asyncio.to_thread(rerank, req.question, candidates, s.top_k_rerank)

    # 4. Generate: LLM answers grounded ONLY in those top-5 chunks.
    with track_stage("generate"):
        answer = await generate(req.question, [c["content"] for c in top])

    sources = [
        Source(content=c["content"], metadata=c["metadata"], score=round(c["rerank_score"], 4))
        for c in top
    ]
    result = QueryResponse(question=req.question, answer=answer, sources=sources)

    # 5. Cache the answer for next time.
    if s.cache_enabled:
        try:
            await redis.setex(key, s.cache_ttl_seconds, result.model_dump_json(exclude={"cached"}))
        except Exception:
            pass

    return result
