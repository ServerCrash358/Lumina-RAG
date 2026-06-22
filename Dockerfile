# Dockerfile — multi-stage build.
#
# Stage 1 (builder) installs dependencies into a venv using uv.
# Stage 2 (runtime) copies only the venv + app code into a slim image and runs
# as a non-root user. Build tooling never ships to production.

# ── builder ──────────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml ./
# Install the CPU-only torch FIRST from PyTorch's CPU index. The default Linux
# torch wheel bundles ~6GB of CUDA libraries we never use (generation happens on
# the host GPU via Ollama; in-container we only run the small embedder/reranker
# on CPU). Pre-installing the +cpu build keeps the image ~3x smaller.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv venv /app/.venv && \
    uv pip install --python /app/.venv torch --index-url https://download.pytorch.org/whl/cpu && \
    uv pip install --python /app/.venv -r pyproject.toml
COPY app ./app

# ── runtime ────────────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime
RUN useradd --create-home --uid 1000 appuser
WORKDIR /app
COPY --from=builder --chown=appuser:appuser /app/.venv /app/.venv
COPY --from=builder --chown=appuser:appuser /app/app  /app/app
# Pre-create the HuggingFace cache dir owned by appuser. When the named volume
# mounts here on first run, Docker seeds it from this dir, so it stays writable
# by the non-root user (avoids the classic "named volume owned by root" error).
RUN mkdir -p /home/appuser/.cache/huggingface && chown -R appuser:appuser /home/appuser/.cache
ENV PATH="/app/.venv/bin:$PATH" \
    HF_HOME="/home/appuser/.cache/huggingface"
USER appuser
EXPOSE 8000
# Exec form so uvicorn is PID 1 and receives SIGTERM for graceful shutdown.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
