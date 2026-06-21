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
RUN --mount=type=cache,target=/root/.cache/uv \
    uv venv /app/.venv && \
    uv pip install --python /app/.venv -r pyproject.toml
COPY app ./app

# ── runtime ────────────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime
RUN useradd --create-home --uid 1000 appuser
WORKDIR /app
COPY --from=builder --chown=appuser:appuser /app/.venv /app/.venv
COPY --from=builder --chown=appuser:appuser /app/app  /app/app
ENV PATH="/app/.venv/bin:$PATH"
USER appuser
EXPOSE 8000
# Exec form so uvicorn is PID 1 and receives SIGTERM for graceful shutdown.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
