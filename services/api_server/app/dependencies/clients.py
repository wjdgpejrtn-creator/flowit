from __future__ import annotations

import logging

import httpx
import redis.asyncio as aioredis
from fastapi import Request

from app.config import Settings

logger = logging.getLogger(__name__)


_REDIS_SCHEMES = ("redis://", "rediss://", "unix://")


async def init_redis(settings: Settings) -> aioredis.Redis | None:
    url = (settings.redis_url or "").strip()
    if not url:
        logger.warning("Redis: REDIS_URL 미설정 — init skip (REQ-011 infra 구축 전 단계)")
        return None
    if not url.startswith(_REDIS_SCHEMES):
        logger.warning(
            "Redis: REDIS_URL scheme invalid (must start with %s) — init skip. Got: %r",
            "/".join(_REDIS_SCHEMES),
            url[:40],
        )
        return None
    client = aioredis.from_url(url, decode_responses=True)
    await client.ping()
    logger.info("Redis connected: %s", url)
    return client


async def dispose_redis(client: aioredis.Redis | None) -> None:
    if client is not None:
        await client.aclose()


_HTTP_SCHEMES = ("http://", "https://")


def init_orchestrator_http(settings: Settings) -> httpx.AsyncClient | None:
    url = (settings.orchestrator_url or "").strip()
    if not url:
        logger.warning("Orchestrator: ORCHESTRATOR_URL 미설정 — init skip (Phase E 전 단계)")
        return None
    if not url.startswith(_HTTP_SCHEMES):
        logger.warning(
            "Orchestrator: ORCHESTRATOR_URL scheme invalid (must start with http://|https://) — init skip. Got: %r",
            url[:40],
        )
        return None
    return httpx.AsyncClient(
        base_url=url,
        timeout=httpx.Timeout(settings.orchestrator_timeout_s, connect=10.0),
    )


async def dispose_orchestrator_http(client: httpx.AsyncClient | None) -> None:
    if client is not None:
        await client.aclose()


def get_redis(request: Request) -> aioredis.Redis | None:
    # lifespan 미진입(TestClient의 단일 요청 mode) 경로에서도 안전한 fallback
    return getattr(request.app.state, "redis", None)


def get_orchestrator_http(request: Request) -> httpx.AsyncClient | None:
    return getattr(request.app.state, "orchestrator_http", None)
