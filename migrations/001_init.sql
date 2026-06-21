-- 001_init.sql — the pgvector data layer.
--
-- This is the heart of Step 1: the table RAG retrieves from. It's the capstone's
-- documents table (roadmap p20): content + metadata + a 1536-dim embedding, with
-- an HNSW index for fast approximate-nearest-neighbour search.

-- pgvector ships the `vector` type + ANN index methods. Enable it once.
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS documents (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    content    TEXT        NOT NULL,           -- the chunk of text we embed + retrieve
    metadata   JSONB       NOT NULL DEFAULT '{}'::jsonb,  -- source, title, chunk index, etc.
    embedding  vector(384),                    -- BAAI/bge-small-en-v1.5 dimensionality
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- HNSW index for fast ANN search.
--   vector_cosine_ops  → distance metric is cosine (matches OpenAI embeddings,
--                        which are normalised, so cosine ≈ dot product).
--   m = 16             → graph connectivity (higher = better recall, more memory).
--   ef_construction=64 → build-time search width (higher = better graph, slower build).
-- These are pgvector's sane defaults; we'll tune ef_search at query time in Step 3.
CREATE INDEX IF NOT EXISTS idx_documents_embedding_hnsw
    ON documents
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- GIN index on metadata so we can filter retrieval by source/tags later.
CREATE INDEX IF NOT EXISTS idx_documents_metadata
    ON documents USING gin (metadata);
