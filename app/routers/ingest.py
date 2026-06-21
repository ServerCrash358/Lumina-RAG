"""
ingest.py — POST /ingest: chunk → embed → store.

The ingestion path of RAG. For each document: split into overlapping chunks,
embed every chunk with the local model, and bulk-insert (content, metadata,
embedding) rows into `documents`. Those rows are what retrieval searches later.

Embedding is CPU/GPU-bound and synchronous, so we run it in a worker thread
(asyncio.to_thread) to avoid blocking the event loop while the model crunches.
"""

from __future__ import annotations

import asyncio
import json

import asyncpg
from fastapi import APIRouter, Depends

from app.config import get_settings
from app.db import get_conn
from app.schemas import IngestRequest, IngestResponse
from app.services.chunker import chunk_text
from app.services.embedder import embed_passages

router = APIRouter(tags=["ingest"])


@router.post("/ingest", response_model=IngestResponse)
async def ingest(req: IngestRequest, conn: asyncpg.Connection = Depends(get_conn)) -> IngestResponse:
    s = get_settings()
    rows: list[tuple[str, str, list[float]]] = []

    for doc in req.documents:
        chunks = chunk_text(doc.content, s.chunk_size, s.chunk_overlap)
        if not chunks:
            continue
        # Offload the model work to a thread so we don't stall the event loop.
        vectors = await asyncio.to_thread(embed_passages, chunks)
        for idx, (chunk, vec) in enumerate(zip(chunks, vectors)):
            meta = {**doc.metadata, "chunk_index": idx, "n_chunks": len(chunks)}
            rows.append((chunk, json.dumps(meta), vec))

    if rows:
        # One round-trip for all chunks. $3 is a Python list → pgvector codec
        # (registered in db.py) encodes it as vector(384).
        await conn.executemany(
            "INSERT INTO documents (content, metadata, embedding) "
            "VALUES ($1, $2::jsonb, $3)",
            rows,
        )

    return IngestResponse(documents_received=len(req.documents), chunks_created=len(rows))
