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

## Step 4 — rerank + generate (local LLM via Ollama)

```bash
# 1. Start Ollama (native install → uses the GPU) and pull a small model.
ollama serve            # (background; or the Ollama tray app)
ollama pull llama3.2:1b # ~1.3GB, fits a 4GB GPU

# 2. Bake a fitted context size into a custom model so it offloads fully to GPU.
#    The default num_ctx=4096 makes the KV cache too big for a 4GB card.
#    (Modelfile lives in ollama/Modelfile: FROM llama3.2:1b / PARAMETER num_ctx 2048)
ollama create lumina-llm -f ollama/Modelfile

# 3. Point Lumina at it (.env): LLM_MODEL=lumina-llm  (LLM_BASE_URL stays Ollama's)
#    Restart the API, then:
curl -X POST localhost:8010/query -H 'content-type: application/json' \
  -d '{"question":"How does Lumina keep search fast, and why rerank?"}'
#   -> {question, answer, sources:[{content,metadata,score}], cached:false}
#   Same question again -> cached:true, ~0.3s instead of ~35s.

# Confirm the model is on the GPU, not CPU:
ollama ps          # PROCESSOR should read '100% GPU'
nvidia-smi         # ~1.7GB VRAM used
```

### If the model won't load ("CPU/CUDA_Host buffer" / "paging file too small")
That's a RAM/commit-limit problem, not code. Free physical RAM (close VS Code /
browser) so there's > ~6GB free, and keep num_ctx small. Check with:
```powershell
(Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory/1MB   # GB free
```

## Step 5 — instrumentation (Prometheus metrics)

Port is back to 8000 (yesterday's orphaned socket cleared). Start services:
```bash
docker compose up -d db redis
ollama serve
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

```bash
# Drive some traffic, then scrape metrics:
curl -X POST localhost:8000/query -H 'content-type: application/json' -d '{"question":"..."}'
curl localhost:8000/metrics

# The useful series:
#   http_request_duration_seconds_*  → p50/p95/p99 latency, by route
#   http_requests_total{status=~"5.."} → error rate
#   rag_cache_hits_total / rag_cache_misses_total → cache hit rate
#   rag_stage_seconds{stage="embed|retrieve|rerank|generate"} → where time goes
```

Measured steady-state per-stage (2nd call, models warm):
  embed ~32ms · retrieve ~4ms · rerank ~181ms · generate ~2.1s
(First call's rerank shows ~9.5s — that's the one-time cross-encoder model load.)

## Step 6 — containerise the full app

The whole app (FastAPI + embedder + reranker) now runs in Docker; the LLM stays
on the host via Ollama, reached at `host.docker.internal:11434`.

```bash
# Stop any host uvicorn on 8000 first, then:
docker compose up -d --build      # api + db + redis, all containerised
curl localhost:8000/health/ready
curl -X POST localhost:8000/query -H 'content-type: application/json' -d '{"question":"..."}'
```

Key points baked in:
- **CPU-only torch** in the image (`--index-url .../whl/cpu`) → image is **1.6GB**,
  not 8GB (the default Linux torch bundles ~6GB of unused CUDA libs).
- **HF model cache volume** (`hf_cache`) persists the embedder+reranker (~217MB)
  so restarts don't re-download.
- **`EMBED_DEVICE=cpu`** in-container; generation delegated to host GPU Ollama via
  **`LLM_BASE_URL=http://host.docker.internal:11434/v1`** + `extra_hosts: host-gateway`.

```bash
docker compose down      # stop everything (keeps pgdata + hf_cache volumes)
```

## Step 7a — live Kubernetes deploy (kind)

```bash
# Install kind (single binary), create a cgroup-v1-compatible cluster (k8s 1.30).
curl -sL -o ~/bin/kind.exe https://github.com/kubernetes-sigs/kind/releases/latest/download/kind-windows-amd64
kind create cluster --name lumina --image kindest/node:v1.30.4

# Build + load the app image INTO the cluster (no registry needed locally).
docker compose build api
kind load docker-image lumina-api:latest --name lumina

# Ollama must listen beyond localhost so pods can reach it:
#   (Windows)  set OLLAMA_HOST=0.0.0.0:11434  before `ollama serve`
# Pods reach it at http://host.docker.internal:11434 (works on Docker Desktop).

# Apply everything + wait.
kubectl apply -k k8s/
kubectl -n lumina rollout status deploy/lumina-api

# Test via port-forward.
kubectl -n lumina port-forward svc/lumina-api 8088:80
curl -X POST localhost:8088/query -H 'content-type: application/json' -d '{"question":"..."}'
```

Gotchas hit + fixed:
- **kind 0.32 (k8s 1.34) hard-fails on cgroup v1** (this WSL/Docker setup) →
  used `--image kindest/node:v1.30.4`.
- **`imagePullPolicy: IfNotPresent`** is required — the image is `kind load`-ed,
  not in a registry.
- The api pod restarts a few times at first (fail-fast DB pool racing Postgres
  startup); it self-heals once Postgres is Ready. (An initContainer that waits
  for Postgres would make this clean.)

Cluster teardown: `kind delete cluster --name lumina`

## Step 7b — CI/CD (GitHub Actions) + ArgoCD GitOps

Artifacts (run on GitHub / in-cluster, not your laptop):
- `.github/workflows/ci-cd.yaml` — push to main → test (ruff + pytest) → build →
  push image to **GHCR** → rewrite the image tag in `k8s/deployment.yaml` + commit.
- `argocd/application.yaml` — ArgoCD watches `k8s/` on main and auto-syncs.

```bash
# Local validation (no Docker needed):
uv run --with pytest pytest tests/ -q          # 5 passed

# CI runs automatically on push. Image lands at:
#   ghcr.io/servercrash358/lumina-api:<sha>

# Bring ArgoCD live in the kind cluster (one-time bootstrap):
kubectl create namespace argocd
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml
kubectl -n argocd rollout status deploy/argocd-server
kubectl apply -f argocd/application.yaml         # ArgoCD now reconciles k8s/ from git
```

Notes when going live:
- **GHCR images are private by default.** For the cluster to pull, either make the
  package public (GitHub → Packages → lumina-api → Public) or add an imagePullSecret.
- For **local kind**, keep using the locally-built image:
  `docker build -t ghcr.io/servercrash358/lumina-api:latest . && kind load docker-image ghcr.io/servercrash358/lumina-api:latest`
  (imagePullPolicy IfNotPresent uses the loaded image, no pull needed).

## Step 8 — eval + automation (metrics + MLflow + Prefect)

```bash
uv pip install -e ".[eval]"        # httpx + mlflow + prefect (host-only)

# With the API up (local or k8s), run the eval — it ingests a golden corpus,
# then measures retrieval recall@k / MRR and answer keyword-coverage + latency.
python evals/run_eval.py --base-url http://localhost:8000
mlflow ui                           # view logged runs at localhost:5000 (./mlruns)

# Automate it (ingest -> eval -> quality gate), once or on a daily cron:
python pipelines/eval_pipeline.py            # run once
python pipelines/eval_pipeline.py --serve    # schedule (cron 0 2 * * *)
```
Free + deterministic: metrics use the system's own outputs (no paid LLM judge).
RAGAS' faithfulness/answer-relevancy can be added by pointing it at Ollama.

## Step 9 — cloud infrastructure (Terraform / AWS)

```bash
cd terraform
terraform fmt -check && terraform init -backend=false && terraform validate

# To actually provision (needs AWS creds; costs money — not run here):
export TF_VAR_db_password=...        # or TF_VAR_db_password in env
terraform init && terraform apply
aws eks update-kubeconfig --name lumina --region ap-south-1
# Then deploy the SAME k8s/ manifests, or let ArgoCD sync them.
```
Provisions: VPC + EKS + RDS Postgres (pgvector) + ElastiCache Redis + ECR.
On AWS there's no host GPU → switch generation to Amazon Bedrock / a cloud LLM
(one config line — the generator is OpenAI-compatible).

---
*Log: ALL 9 STEPS DONE. Lumina is a complete, locally-runnable, cloud-ready RAG system.*
