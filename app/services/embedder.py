"""
embedder.py — local, no-cost text embeddings via sentence-transformers.

Model: BAAI/bge-small-en-v1.5 (384-dim). Runs on CPU by default (fast for a
model this small) and auto-uses CUDA if a GPU build of torch is installed.

Two important details for bge models:
  * Embeddings are L2-NORMALISED, so cosine similarity == dot product. Our HNSW
    index uses vector_cosine_ops, so this is the right metric.
  * It's an ASYMMETRIC model: queries get an instruction prefix, passages don't.
    Hence two functions — embed_passages (ingest) and embed_query (search).
"""

from __future__ import annotations

import logging
from functools import lru_cache

from app.config import get_settings

log = logging.getLogger("lumina.embedder")


def _resolve_device(pref: str) -> str:
    if pref != "auto":
        return pref
    try:
        import torch

        return "cuda" if torch.cuda.is_available() else "cpu"
    except Exception:
        return "cpu"


@lru_cache(maxsize=1)
def _model():
    # Imported lazily + cached so the (heavy) load happens once, on first use,
    # not at module import or on every request.
    from sentence_transformers import SentenceTransformer

    s = get_settings()
    device = _resolve_device(s.embed_device)
    log.info("loading embedding model %s on %s", s.embedding_model, device)
    return SentenceTransformer(s.embedding_model, device=device)


def embed_passages(texts: list[str]) -> list[list[float]]:
    """Embed document chunks for storage. Returns normalised 384-dim vectors."""
    if not texts:
        return []
    vecs = _model().encode(
        texts, normalize_embeddings=True, convert_to_numpy=True, batch_size=32
    )
    return [v.tolist() for v in vecs]


def embed_query(text: str) -> list[float]:
    """Embed a search query (with the bge instruction prefix). Used in Step 3."""
    s = get_settings()
    vec = _model().encode(
        [s.bge_query_prefix + text], normalize_embeddings=True, convert_to_numpy=True
    )[0]
    return vec.tolist()
