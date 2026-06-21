# Lumina — Command Log

Every command used to build, run, and verify the project, in order. Reproduce
Step 1 by running these from the `lumina/` directory.

## Prerequisites
- Docker Desktop running
- `uv` (for host-side runs/tests; optional in Step 1)

## Step 1 — bring up the data layer + app

```bash
# 1. Build images and start Postgres (pgvector), Redis, and the API.
#    --build rebuilds the api image; -d runs detached.
docker compose up --build -d

# 2. Wait for readiness, then hit the endpoints.
curl localhost:8001/                 # {"name":"lumina","status":"ok","docs":"/docs"}
curl localhost:8001/health/live      # {"status":"alive"}
curl localhost:8001/health/ready     # {"status":"ready"}  (checks Postgres)

# 3. Verify the pgvector schema was created on first DB init.
docker exec lumina-db-1 psql -U lumina -d lumina -c "\dx vector"
docker exec lumina-db-1 psql -U lumina -d lumina -c "\d documents"
```

Expected schema: extension `vector` present; `documents` table with
`embedding vector(1536)`, an HNSW index (`idx_documents_embedding_hnsw`), and a
GIN index on `metadata`.

## Rebuild after a code change

```bash
docker compose up -d --build api     # rebuild + restart only the API
```

## Open the interactive API docs
```
http://localhost:8001/docs
```

## Stop / clean up

```bash
docker compose down                  # stop containers (keeps the pgdata volume)
docker compose down -v               # also delete the DB volume (fresh schema next up)
```

## Ports (offset to avoid clashing with other local projects)
| Service  | Host port | Container |
|----------|-----------|-----------|
| API      | 8001      | 8000      |
| Postgres | 5435      | 5432      |
| Redis    | 6380      | 6379      |

## Step 2 — ingestion (local embeddings, no API cost)

Dev workflow change: the API now runs **on the host** (so it can use the GPU and
to avoid baking torch into the image), while Postgres + Redis stay in Docker.

```bash
# 1. The embedding dim changed 1536 -> 384, so recreate the (empty) DB volume.
docker compose down -v
docker compose up -d db redis            # only infra in Docker now

# 2. Install host deps (pulls torch — CPU build by default on Windows).
uv sync --all-extras

# 3. (optional) Check whether torch sees a GPU.
uv run python -c "import torch; print(torch.__version__, torch.cuda.is_available())"
#   -> 2.12.1+cpu False   (CPU build; fast enough for bge-small. See GPU note below.)

# 4. Run the API on the host.
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000

# 5. Ingest documents (first call downloads the model ~130MB, once).
curl -X POST localhost:8000/ingest -H 'content-type: application/json' -d '{
  "documents": [{"content": "your text here", "metadata": {"source": "demo"}}]
}'
#   -> {"documents_received":1,"chunks_created":N}

# 6. Verify rows + 384-dim embeddings landed.
docker exec lumina-db-1 psql -U lumina -d lumina -c \
  "SELECT left(content,40), vector_dims(embedding) FROM documents;"
```

### GPU note (optional — not needed for this small model)
The default torch is the **CPU** build. bge-small runs fine on CPU. To use your
RTX 2050 instead, install the CUDA build of torch (it auto-activates via
`embed_device=auto`):
```bash
uv pip install torch --index-url https://download.pytorch.org/whl/cu124
```

## Step 3 — retrieval (pgvector ANN over HNSW)

```bash
# API auto-reloads now (started with --reload). If it's not running:
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

# Semantic search — embeds the query and ranks chunks by cosine similarity.
curl -X POST localhost:8000/search -H 'content-type: application/json' \
  -d '{"query":"how does fast vector search scale?","top_k":3}'
#   -> {"query":..., "count":3, "results":[{id, content, metadata, score}, ...]}

# Confirm the HNSW index is actually used for the similarity ordering.
docker exec lumina-db-1 psql -U lumina -d lumina -c \
  "EXPLAIN ANALYZE SELECT id FROM documents
   ORDER BY embedding <=> (SELECT embedding FROM documents LIMIT 1) LIMIT 3;"
#   -> 'Index Scan using idx_documents_embedding_hnsw'
```

`<=>` = cosine distance; score = `1 - distance` (1.0 = identical). `hnsw.ef_search`
(config: HNSW_EF_SEARCH=64) tunes recall vs speed at query time.

---
*Log: Steps 1–3 done. Next: Step 4 (cross-encoder rerank + LLM generate → /query).*
