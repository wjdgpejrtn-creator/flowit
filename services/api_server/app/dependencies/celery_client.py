from __future__ import annotations

import logging

from celery import Celery
from fastapi import HTTPException, Request

from app.config import Settings

logger = logging.getLogger(__name__)


def init_celery(settings: Settings) -> Celery | None:
    """Celery 클라이언트 초기화. dispatch 전용 (execution_engine import 0건 — task name 문자열).

    REDIS_URL 미설정(REQ-011 infra 구축 전) 시 None 반환 → 라우터가 503으로 graceful 처리.
    """
    if not settings.redis_url or not settings.redis_url.startswith(("redis://", "rediss://", "unix://")):
        logger.warning("Celery: REDIS_URL 미설정 또는 invalid — dispatch 비활성")
        return None
    client = Celery("api_server", broker=settings.redis_url)
    logger.info("Celery dispatcher 준비됨 (broker=%s)", settings.redis_url)
    return client


def get_celery(request: Request) -> Celery:
    client = getattr(request.app.state, "celery", None)
    if client is None:
        raise HTTPException(
            status_code=503,
            detail="Celery broker(REDIS_URL) 미설정 — REQ-011 infra 구축 후 사용 가능",
        )
    return client
