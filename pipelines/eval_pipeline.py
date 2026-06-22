"""
eval_pipeline.py — Prefect flow that automates the eval loop.

Mirrors the roadmap's daily pipeline: ingest the latest corpus → run the eval →
log metrics → fail loudly if quality regresses. Run it once, or `.serve()` it on
a cron schedule so it re-runs automatically and you always have fresh numbers.

Run once:
    python pipelines/eval_pipeline.py

Schedule (daily 02:00), keeps running and triggers itself:
    python pipelines/eval_pipeline.py --serve
"""

from __future__ import annotations

import sys

from prefect import flow, task

# Reuse the eval logic so there's a single source of truth.
sys.path.append("evals")
from run_eval import evaluate  # noqa: E402

BASE_URL = "http://localhost:8000"

# Quality gates — the pipeline FAILS if the system regresses below these.
MIN_RECALL = 0.8
MIN_COVERAGE = 0.5


@task(retries=2, retry_delay_seconds=30)
def run_rag_eval(base_url: str) -> dict:
    return evaluate(base_url)


@task
def check_gates(metrics: dict) -> None:
    problems = []
    if metrics["recall_at_k"] < MIN_RECALL:
        problems.append(f"recall_at_k {metrics['recall_at_k']:.2f} < {MIN_RECALL}")
    if metrics["answer_keyword_coverage"] < MIN_COVERAGE:
        problems.append(f"coverage {metrics['answer_keyword_coverage']:.2f} < {MIN_COVERAGE}")
    if problems:
        raise ValueError("Quality gate failed: " + "; ".join(problems))


@flow(name="lumina-eval-pipeline", log_prints=True)
def eval_pipeline(base_url: str = BASE_URL) -> dict:
    metrics = run_rag_eval(base_url)
    print("metrics:", metrics)
    check_gates(metrics)
    print("all quality gates passed")
    return metrics


if __name__ == "__main__":
    if "--serve" in sys.argv:
        # Deploy on a daily cron; the process stays up and re-runs on schedule.
        eval_pipeline.serve(name="daily-eval", cron="0 2 * * *")
    else:
        eval_pipeline()
