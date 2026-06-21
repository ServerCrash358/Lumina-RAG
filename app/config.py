"""
config.py — typed application settings, loaded from environment variables.

Single source of truth for config. pydantic-settings validates and coerces at
startup, so a missing/garbage value fails loudly at boot rather than mid-request.
Many of these fields aren't used until later steps (embedding/LLM/retrieval) —
they're defined now so the contract is clear and the later steps just read them.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # ── application ──────────────────────────────────────────────────────
    app_name: str = "lumina"
    app_env: str = "development"
    log_level: str = "info"

    # ── data layer (Step 1) ──────────────────────────────────────────────
    database_url: str = Field(
        default="postgresql://lumina:lumina@localhost:5435/lumina",
        description="Postgres (pgvector) DSN consumed by asyncpg.create_pool()",
    )
    pool_min_size: int = 2
    pool_max_size: int = 10
    command_timeout: float = 30.0

    redis_url: str = "redis://localhost:6380/0"
    cache_ttl_seconds: int = 3600

    # ── embeddings (Step 2) — LOCAL model, no API cost ───────────────────
    # bge-small-en-v1.5: 384-dim, ~130MB, <1GB VRAM — light enough for any
    # laptop GPU and fast on CPU. embedding_dim MUST match migrations/001_init.sql.
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_dim: int = 384
    embed_device: str = "auto"    # "auto" → cuda if available else cpu; or force "cpu"/"cuda"
    # bge models want this instruction prefix on QUERIES only (not passages).
    bge_query_prefix: str = "Represent this sentence for searching relevant passages: "

    # chunking (Step 2)
    chunk_size: int = 800         # ~target characters per chunk
    chunk_overlap: int = 120      # characters shared between adjacent chunks

    # ── retrieval (Step 3) ───────────────────────────────────────────────
    top_k_retrieve: int = 20      # stage 1: pgvector ANN candidates returned
    # HNSW query-time search width. Higher = better recall, slightly slower.
    # Must be >= the number of rows you want back. Default 40 in pgvector.
    hnsw_ef_search: int = 64

    # ── rerank (Step 4) ──────────────────────────────────────────────────
    reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    top_k_rerank: int = 5         # stage 2: cross-encoder survivors

    # ── generation (Step 4) — OpenAI-compatible, defaults to local Ollama ─
    llm_base_url: str = "http://localhost:11434/v1"   # Ollama's OpenAI-compatible API
    llm_api_key: str | None = None                    # ignored by Ollama; set for cloud
    llm_model: str = "llama3.2:3b"
    llm_temperature: float = 0.1                       # low → faithful, less invention
    llm_max_tokens: int = 512
    cache_enabled: bool = True                         # Redis answer cache


@lru_cache
def get_settings() -> Settings:
    """Cached singleton: env is parsed once, on first call."""
    return Settings()
