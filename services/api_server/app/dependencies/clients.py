from __future__ import annotations

import logging

import httpx
import redis.asyncio as aioredis
from fastapi import Request

from app.config import Settings

logger = logging.getLogger(__name__)


async def init_redis(settings: Settings) -> aioredis.Redis:
    client = aioredis.from_url(settings.redis_url, decode_responses=True)
    await client.ping()
    logger.info("Redis connected: %s", settings.redis_url)
    return client


async def dispose_redis(client: aioredis.Redis) -> None:
    await client.aclose()


def init_orchestrator_http(settings: Settings) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=settings.orchestrator_url,
        timeout=httpx.Timeout(settings.orchestrator_timeout_s, connect=10.0),
    )


async def dispose_orchestrator_http(client: httpx.AsyncClient) -> None:
    await client.aclose()


def get_redis(request: Request) -> aioredis.Redis:
    return request.app.state.redis


def get_orchestrator_http(request: Request) -> httpx.AsyncClient:
    return request.app.state.orchestrator_http
