"""
reranker.py — stage-2 reranking with a cross-encoder.

Stage-1 retrieval (retriever.py) embeds the query and each document INDEPENDENTLY,
then compares vectors — fast, but the model never sees the query and a document
together, so it misses fine-grained relevance. A CROSS-ENCODER does: it feeds
[query, document] as ONE input and runs full attention across both, producing a
much sharper relevance score. The catch — it can't pre-compute, so it's too slow
to run over the whole corpus. Hence the two-stage design:

    bi-encoder ANN  → top-20 candidates  (recall, milliseconds)
    cross-encoder   → top-5 best         (precision, ~tens of ms for 20 pairs)

ms-marco-MiniLM-L-6-v2 is ~80MB and runs comfortably on CPU.
"""

from __future__ import annotations

import logging
from functools import lru_cache

from app.config import get_settings

log = logging.getLogger("lumina.reranker")


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
    from sentence_transformers import CrossEncoder

    s = get_settings()
    device = _resolve_device(s.embed_device)
    log.info("loading reranker %s on %s", s.reranker_model, device)
    return CrossEncoder(s.reranker_model, device=device)


def rerank(query: str, candidates: list[dict], top_k: int) -> list[dict]:
    """Re-score (query, chunk) pairs with the cross-encoder; return the top_k.

    Each candidate is a dict with at least a "content" key. The returned dicts
    are the same objects with a "rerank_score" added, sorted best-first.
    """
    if not candidates:
        return []
    pairs = [(query, c["content"]) for c in candidates]
    scores = _model().predict(pairs)  # higher = more relevant
    for c, score in zip(candidates, scores):
        c["rerank_score"] = float(score)
    candidates.sort(key=lambda c: c["rerank_score"], reverse=True)
    return candidates[:top_k]
