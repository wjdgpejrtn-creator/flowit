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
    # `rediss://`(TLS) 사용 시 Memorystore SERVER_AUTHENTICATION cert는 Google 사설 CA로 서명되어
    # 컨테이너 system trust store에 없음. ssl_cert_reqs=None으로 cert 검증 skip — TLS encryption은
    # 유지. production에서는 server-ca-cert를 image에 COPY하는 정공법 적용 권장 ([[cloud_run_worker_deploy]]).
    kwargs: dict = {"decode_responses": True}
    if url.startswith("rediss://"):
        kwargs["ssl_cert_reqs"] = None
    client = aioredis.from_url(url, **kwargs)
    await client.ping()
    logger.info("Redis connected: %s", url[:40])
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


def init_skills_builder_http(settings: Settings) -> httpx.AsyncClient | None:
    """Skills Builder Sub-Agent 직결 클라이언트 — SOP 문서→스킬 추출(extract) SSE 프록시용.

    orchestrator(intent 분류 경유)와 별도 — 추출은 문서 기반 결정적 흐름이라 skills-builder
    `/v1/agent/route`(source_type="sop", step="extract")를 직접 호출한다. 미설정 시 None →
    `/extract` 라우트가 503으로 graceful 응답 (orchestrator 패턴과 동일).
    """
    url = (settings.skills_builder_url or "").strip()
    if not url:
        logger.warning("SkillsBuilder: SKILLS_BUILDER_URL 미설정 — init skip (extract 비활성)")
        return None
    if not url.startswith(_HTTP_SCHEMES):
        logger.warning(
            "SkillsBuilder: SKILLS_BUILDER_URL scheme invalid (must start with http://|https://) — init skip. Got: %r",
            url[:40],
        )
        return None
    return httpx.AsyncClient(
        base_url=url,
        timeout=httpx.Timeout(settings.skills_builder_timeout_s, connect=10.0),
    )


async def dispose_skills_builder_http(client: httpx.AsyncClient | None) -> None:
    if client is not None:
        await client.aclose()


def get_redis(request: Request) -> aioredis.Redis | None:
    # lifespan 미진입(TestClient의 단일 요청 mode) 경로에서도 안전한 fallback
    return getattr(request.app.state, "redis", None)


def get_orchestrator_http(request: Request) -> httpx.AsyncClient | None:
    return getattr(request.app.state, "orchestrator_http", None)


def get_skills_builder_http(request: Request) -> httpx.AsyncClient | None:
    return getattr(request.app.state, "skills_builder_http", None)
