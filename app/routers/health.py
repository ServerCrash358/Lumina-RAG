"""
health.py — liveness vs readiness. The distinction is critical for Kubernetes.

  /health/live   — "is the process alive?" No dependencies checked. If this
                   fails, k8s RESTARTS the pod. It must NOT touch the DB, or a
                   brief DB blip would trigger pointless restart storms.

  /health/ready  — "can it serve traffic?" Checks Postgres. If this fails, k8s
                   pulls the pod OUT of the load-balancer rotation but leaves it
                   running, so it can recover and rejoin.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response
import asyncpg

from app.db import get_conn

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live")
async def live() -> dict[str, str]:
    return {"status": "alive"}


@router.get("/ready")
async def ready(response: Response, conn: asyncpg.Connection = Depends(get_conn)) -> dict[str, str]:
    try:
        await conn.execute("SELECT 1")
        return {"status": "ready"}
    except Exception:
        response.status_code = 503
        return {"status": "not ready"}
