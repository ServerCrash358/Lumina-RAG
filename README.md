# Lumina

A production **RAG (Retrieval-Augmented Generation) API** that answers questions
grounded in your own documents — built the way it would run in production:
async FastAPI, PostgreSQL + **pgvector** (HNSW ANN), Redis cache, two-stage
retrieval (vector search → cross-encoder rerank), containerised, deployed to
Kubernetes via GitOps, and fully observable.

> **Status: Steps 1–3 of 9 complete** — app skeleton, pgvector data layer,
> local-embedding ingestion (`POST /ingest`), and vector retrieval (`POST /search`,
> HNSW ANN) are live. See the build plan below.

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
| 4 | Rerank + generate: cross-encoder → top-5 → LLM + cache. `POST /query` | ⬜ |
| 5 | Instrument: `/metrics`, OpenTelemetry traces, logs | ⬜ |
| 6 | Containerise (done early here) + harden | ◑ |
| 7 | Kubernetes + CI/CD + ArgoCD GitOps | ⬜ |
| 8 | Eval + automate: MLflow + RAGAS + Prefect daily pipeline | ⬜ |
| 9 | Cloud (Terraform/AWS) + k6 load test + collect metrics | ⬜ |

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
  main.py        # FastAPI app, lifespan (pg pool + redis)
  config.py      # pydantic-settings (DB, Redis, embedding/LLM/retrieval knobs)
  db.py          # asyncpg pool + per-request dependency (pgvector hook ready)
  routers/
    health.py    # /health/live (no DB) + /health/ready (checks DB)
migrations/
  001_init.sql   # CREATE EXTENSION vector; documents table; HNSW + GIN indexes
docker-compose.yml   # api + postgres(pgvector) + redis
Dockerfile           # multi-stage, non-root runtime
```

## Config

All settings come from env vars (see `.env.example`). When running via
`docker compose`, the API reads config from the compose `environment:` block
(hosts are service names `db`/`redis`); the `.env` file is for host-side runs
and uses the published ports (`5435`/`6380`).
