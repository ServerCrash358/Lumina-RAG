"""
run_eval.py — evaluate the deployed RAG system against a golden set.

Metrics (all computable WITHOUT a paid LLM judge, so eval is free + deterministic):
  RETRIEVAL  recall@k  — did the expected source chunk make the top-k?
             MRR        — 1/rank of the expected source (rewards ranking it high)
  ANSWER     keyword coverage — fraction of expected keywords present in the answer
             latency    — wall-clock per /query

This is a lightweight stand-in for RAGAS. RAGAS' faithfulness/answer-relevancy
metrics need an LLM-as-judge; you can swap those in by pointing RAGAS at the same
Ollama endpoint, at the cost of speed. The retrieval metrics here are the ones
that catch the most real regressions anyway.

Results are logged to MLflow using a LOCAL file store (./mlruns) — no server,
no cost. Open them later with `mlflow ui`.

Usage:
    python evals/run_eval.py --base-url http://localhost:8000
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import httpx

HERE = Path(__file__).parent


def _load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def ingest_corpus(client: httpx.Client, corpus: list[dict]) -> None:
    client.post("/ingest", json={"documents": corpus}, timeout=120).raise_for_status()


def evaluate(base_url: str, top_k: int = 5) -> dict:
    corpus = _load_jsonl(HERE / "corpus.jsonl")
    golden = _load_jsonl(HERE / "golden.jsonl")

    with httpx.Client(base_url=base_url) as client:
        ingest_corpus(client, corpus)  # make eval self-contained + reproducible

        hits, recip_ranks, coverages, latencies = [], [], [], []
        for item in golden:
            # --- retrieval ---
            r = client.post("/search", json={"query": item["question"], "top_k": top_k}, timeout=60)
            results = r.json()["results"]
            rank = next((i + 1 for i, h in enumerate(results)
                         if h["metadata"].get("source") == item["expected_source"]), None)
            hits.append(1 if rank else 0)
            recip_ranks.append(1.0 / rank if rank else 0.0)

            # --- answer ---
            t0 = time.perf_counter()
            q = client.post("/query", json={"question": item["question"]}, timeout=180)
            latencies.append(time.perf_counter() - t0)
            answer = q.json()["answer"].lower()
            kw = item["expected_keywords"]
            coverages.append(sum(k.lower() in answer for k in kw) / len(kw))

    n = len(golden)
    return {
        "n": n,
        "recall_at_k": sum(hits) / n,
        "mrr": sum(recip_ranks) / n,
        "answer_keyword_coverage": sum(coverages) / n,
        "mean_query_latency_s": sum(latencies) / n,
        "top_k": top_k,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://localhost:8000")
    ap.add_argument("--top-k", type=int, default=5)
    args = ap.parse_args()

    metrics = evaluate(args.base_url, args.top_k)
    print("\n=== Lumina RAG eval ===")
    for k, v in metrics.items():
        print(f"  {k:28} {v:.4f}" if isinstance(v, float) else f"  {k:28} {v}")

    # Log to MLflow's local file store (./mlruns). No server needed.
    try:
        import mlflow

        with mlflow.start_run(run_name="lumina-eval"):
            mlflow.log_params({"top_k": args.top_k, "embedding_model": "bge-small-en-v1.5",
                               "reranker": "ms-marco-MiniLM-L-6-v2"})
            mlflow.log_metrics({k: v for k, v in metrics.items() if isinstance(v, float)})
        print("\n  logged to MLflow (./mlruns) — view with: mlflow ui")
    except ImportError:
        print("\n  (mlflow not installed; skipped logging. `uv pip install mlflow` to enable.)")


if __name__ == "__main__":
    main()
