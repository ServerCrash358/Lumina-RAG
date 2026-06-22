"""
metrics.py — Prometheus metrics + the ASGI middleware that records them.

What these power (the roadmap's interview numbers + Grafana panels):
  p50/p95/p99 latency  ← HTTP_REQUEST_DURATION (Histogram)
  error rate           ← HTTP_REQUESTS_TOTAL{status=~"5.."} / total
  cache hit rate       ← RAG_CACHE_HITS / (HITS + MISSES)
  per-stage cost       ← RAG_STAGE_SECONDS{stage="embed|retrieve|rerank|generate"}

The per-stage histogram is the interesting, RAG-specific one: it tells you where
a /query actually spends its time (almost always: generate >> rerank > the rest),
which is the first thing an interviewer asks about latency.
"""

from __future__ import annotations

import time
from contextlib import contextmanager

from prometheus_client import Counter, Histogram
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# ── HTTP-level metrics ─────────────────────────────────────────────────────
HTTP_REQUESTS_TOTAL = Counter(
    "http_requests_total", "Total HTTP requests", ["method", "path", "status"]
)
HTTP_REQUEST_DURATION = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "path"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
)

# ── RAG-specific metrics ───────────────────────────────────────────────────
RAG_CACHE_HITS = Counter("rag_cache_hits_total", "Answer-cache hits")
RAG_CACHE_MISSES = Counter("rag_cache_misses_total", "Answer-cache misses")
RAG_STAGE_SECONDS = Histogram(
    "rag_stage_seconds",
    "Time spent in each RAG stage",
    ["stage"],  # embed | retrieve | rerank | generate
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0),
)


@contextmanager
def track_stage(stage: str):
    """Time a RAG stage. Usable around an `await` — the body may be async even
    though the context manager itself is sync."""
    start = time.perf_counter()
    try:
        yield
    finally:
        RAG_STAGE_SECONDS.labels(stage).observe(time.perf_counter() - start)


def _route_template(request: Request) -> str:
    # Use the matched route template ("/documents/{id}"), never the raw URL.
    # An unmatched request (404) carries an arbitrary, attacker-controllable path;
    # labelling by it would let anyone mint unbounded time series. Collapse those.
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    return path if path is not None else "__unmatched__"


class PrometheusMiddleware(BaseHTTPMiddleware):
    """Times every request and records count + duration. Runs for all routes,
    so you can't forget to instrument a new endpoint."""

    async def dispatch(self, request: Request, call_next) -> Response:
        start = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            return response
        finally:
            elapsed = time.perf_counter() - start
            path = _route_template(request)
            HTTP_REQUESTS_TOTAL.labels(request.method, path, str(status)).inc()
            HTTP_REQUEST_DURATION.labels(request.method, path).observe(elapsed)
