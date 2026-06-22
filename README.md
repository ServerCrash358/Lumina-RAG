# Lumina

A production **RAG (Retrieval-Augmented Generation) API** that answers questions
grounded in your own documents — built the way it would run in production:
async FastAPI, PostgreSQL + **pgvector** (HNSW ANN), Redis cache, two-stage
retrieval (vector search → cross-encoder rerank), containerised, deployed to
Kubernetes via GitOps, and fully observable.

> **Status: COMPLETE (all 9 steps).** A full, local-first, cloud-ready RAG
> platform: ingest → embed → HNSW retrieve → cross-encoder rerank → local-LLM
> generate, with caching, Prometheus metrics, containerisation, a live
> Kubernetes deploy (kind), GitHub Actions CI/CD → GHCR, ArgoCD GitOps, an
> automated eval pipeline (MLflow + Prefect), and Terraform for AWS.

## Architecture (target)

```
POST /query → Redis cache? ─ HIT → cached answer
                 │ MISS
                 ▼
            embed query (text-embedding-3-small, 1536-dim)
                 ▼
            pgvector ANN search over HNSW → top-20 candidates   ← recall
                 ▼
            cross-encoder rerank (ms-marco-MiniLM) → top-5       ← precision
                 ▼
            LLM generate (gpt-4o-mini) grounded in top-5 → answer + sources
```

The **rerank** stage is what cuts irrelevant context — fast vector search casts
a wide net (top-20), the slow-but-accurate cross-encoder then keeps only the 5
genuinely relevant chunks before the LLM ever sees them.

## Build plan

| Step | What | State |
|------|------|-------|
| 1 | App skeleton + pgvector data layer (`documents` + HNSW) | ✅ done |
| 2 | Ingestion: chunk → embed (local bge-small) → store. `POST /ingest` | ✅ done |
| 3 | Retrieval: pgvector ANN (HNSW, cosine) → top-20. `POST /search` | ✅ done |
| 4 | Rerank + generate: cross-encoder → top-5 → local LLM + cache. `POST /query` | ✅ done |
| 5 | Instrument: `/metrics` (HTTP + per-stage + cache). OTel traces later | ✅ done |
| 6 | Containerise full app (CPU torch, HF cache vol, host Ollama) | ✅ done |
| 7 | Kubernetes (kind) live + GitHub Actions CI/CD + ArgoCD GitOps | ✅ done |
| 8 | Eval + automate: metrics + MLflow + Prefect quality-gated pipeline | ✅ done |
| 9 | Cloud IaC: Terraform for VPC + EKS + RDS(pgvector) + ElastiCache + ECR | ✅ done |

## Run it (Step 1)

```bash
docker compose up --build -d
curl localhost:8001/health/ready      # {"status":"ready"}
open http://localhost:8001/docs
```

Full command reference: see [COMMANDS.md](COMMANDS.md).

## Layout

```
app/
  main.py            # FastAPI app, lifespan, Prometheus middleware, /metrics
  config.py          # pydantic-settings (all knobs)
  db.py              # asyncpg pool + pgvector codec + dependency
  metrics.py         # Prometheus metrics + per-stage timing
  routers/           # health · ingest · search · query
  services/          # embedder · chunker · retriever · reranker · generator
migrations/001_init.sql   # documents table + HNSW + GIN indexes
tests/               # dependency-free unit tests (run in CI)
evals/               # golden corpus + run_eval.py (recall@k, MRR, coverage)
pipelines/           # Prefect eval pipeline (quality-gated, schedulable)
Dockerfile  docker-compose.yml   # CPU-torch multi-stage image + local stack
k8s/                 # namespace · config · postgres · redis · deployment · svc · hpa
ollama/Modelfile     # local LLM (llama3.2:1b @ num_ctx 2048, fits 4GB GPU)
.github/workflows/   # CI/CD: test → build → GHCR → GitOps bump
argocd/              # ArgoCD Application (auto-sync k8s/ from git)
terraform/           # AWS: VPC · EKS · RDS(pgvector) · ElastiCache · ECR
```

## Config

All settings come from env vars (see `.env.example`). When running via
`docker compose`, the API reads config from the compose `environment:` block
(hosts are service names `db`/`redis`); the `.env` file is for host-side runs
and uses the published ports (`5435`/`6380`).

## Results (measured locally)

| Metric | Value |
|--------|-------|
| Per-stage latency (warm) | embed ~32 ms · retrieve (HNSW) ~4 ms · rerank ~181 ms · generate ~2.1 s |
| DB query tuning (separate proof) | 1,709 ms → 0.36 ms with the right composite index |
| Cache hit | 35 s → 0.33 s on a repeated question |
| App image | 1.6 GB (CPU-torch) vs 8.2 GB default |
| Embeddings cost | $0 — local bge-small (384-dim), runs on CPU or a 4 GB GPU |


