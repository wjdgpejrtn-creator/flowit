from __future__ import annotations

import logging

import httpx
import redis.asyncio as aioredis
from fastapi import Request

from app.config import Settings

logger = logging.getLogger(__name__)


async def init_redis(settings: Settings) -> aioredis.Redis | None:
    if not settings.redis_url:
        logger.warning("Redis: REDIS_URL 미설정 — init skip (REQ-011 infra 구축 전 단계)")
        return None
    client = aioredis.from_url(settings.redis_url, decode_responses=True)
    await client.ping()
    logger.info("Redis connected: %s", settings.redis_url)
    return client


async def dispose_redis(client: aioredis.Redis | None) -> None:
    if client is not None:
        await client.aclose()


def init_orchestrator_http(settings: Settings) -> httpx.AsyncClient | None:
    if not settings.orchestrator_url:
        logger.warning("Orchestrator: ORCHESTRATOR_URL 미설정 — init skip (Phase E 전 단계)")
        return None
    return httpx.AsyncClient(
        base_url=settings.orchestrator_url,
        timeout=httpx.Timeout(settings.orchestrator_timeout_s, connect=10.0),
    )


async def dispose_orchestrator_http(client: httpx.AsyncClient | None) -> None:
    if client is not None:
        await client.aclose()


def get_redis(request: Request) -> aioredis.Redis | None:
    return request.app.state.redis


def get_orchestrator_http(request: Request) -> httpx.AsyncClient | None:
    return request.app.state.orchestrator_http
