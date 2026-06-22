from __future__ import annotations

import asyncio
import logging

import httpx
from fastapi import APIRouter, Depends, Request
from sqlalchemy import text

from app.dependencies.clients import get_orchestrator_http, get_redis
from app.dependencies.database import get_db
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


async def _check_db(session: AsyncSession) -> str:
    try:
        await asyncio.wait_for(session.execute(text("SELECT 1")), timeout=5.0)
        return "ok"
    except Exception as exc:
        logger.exception("health: db failed")
        msg = str(exc) or repr(exc)
        return f"fail:{exc.__class__.__name__}: {msg[:200]}"


async def _check_redis(redis_client: aioredis.Redis | None) -> str:
    if redis_client is None:
        return "skipped"
    try:
        await asyncio.wait_for(redis_client.ping(), timeout=2.0)
        return "ok"
    except Exception as exc:
        logger.warning("health: redis failed: %s", exc)
        return f"fail:{exc.__class__.__name__}"


async def _check_orchestrator(client: httpx.AsyncClient | None) -> str:
    if client is None:
        return "skipped"
    try:
        resp = await client.get("/v1/health", timeout=2.0)
        if resp.status_code < 500:
            return "ok"
        return f"fail:{resp.status_code}"
    except Exception as exc:
        logger.warning("health: orchestrator failed: %s", exc)
        return f"fail:{exc.__class__.__name__}"


@router.get("/health")
async def health(
    request: Request,
    session: AsyncSession = Depends(get_db),
    redis_client: aioredis.Redis | None = Depends(get_redis),
    orchestrator: httpx.AsyncClient | None = Depends(get_orchestrator_http),
) -> dict[str, str]:
    db_status, redis_status, orch_status = await asyncio.gather(
        _check_db(session),
        _check_redis(redis_client),
        _check_orchestrator(orchestrator),
    )
    overall = "ok" if all(s in ("ok", "skipped") for s in (db_status, redis_status, orch_status)) else "degraded"
    return {
        "status": overall,
        "db": db_status,
        "redis": redis_status,
        "orchestrator": orch_status,
        "request_id": getattr(request.state, "request_id", ""),
    }
