from __future__ import annotations

import logging
import secrets

import redis.asyncio as aioredis
from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel

from auth.adapters.oauth.google_oauth_client import GoogleOAuthClient
from auth.application.use_cases.authenticate_use_case import AuthenticateUseCase
from auth.application.use_cases.refresh_token_use_case import RefreshTokenUseCase
from auth.domain.value_objects.token_pair import TokenPair
from common_schemas import PermissionSource

from app.config import Settings
from app.dependencies.auth import (
    get_authenticate_use_case,
    get_google_oauth,
    get_refresh_token_use_case,
)
from app.dependencies.clients import get_redis
from app.dependencies.permission import get_permission_source
from app.dependencies.settings import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

# RFC 6749 §10.12 — OAuth state는 CSRF 방어용 단일 사용 토큰.
# Redis SETEX로 10분 TTL 부여 → callback에서 GETDEL로 검증 + 소진 (replay 방지).
OAUTH_STATE_KEY_PREFIX = "oauth_state:"
OAUTH_STATE_TTL_SECONDS = 600


class LoginRequest(BaseModel):
    code: str


class RefreshRequest(BaseModel):
    refresh_token: str


class AuthorizeResponse(BaseModel):
    authorization_url: str
    state: str


@router.get("/authorize", response_model=AuthorizeResponse)
async def authorize(
    google_oauth: GoogleOAuthClient = Depends(get_google_oauth),
    redis: aioredis.Redis | None = Depends(get_redis),
    settings: Settings = Depends(get_settings),
) -> AuthorizeResponse:
    state = secrets.token_urlsafe(24)

    if redis is not None:
        await redis.setex(f"{OAUTH_STATE_KEY_PREFIX}{state}", OAUTH_STATE_TTL_SECONDS, "1")
    elif settings.is_production():
        # production에서 Redis 없으면 CSRF 보호 불가 → 거부.
        raise HTTPException(status_code=503, detail="OAuth state store unavailable (Redis required in production)")
    else:
        logger.warning("OAuth authorize: Redis 미설정 — state CSRF 검증 비활성 (non-production only)")

    url = google_oauth.authorization_url(state)
    return AuthorizeResponse(authorization_url=url, state=state)


async def _consume_oauth_state(state: str | None, redis: aioredis.Redis | None, settings: Settings) -> None:
    """callback에서 state를 검증 + 일회용 소진. invalid/expired 시 401, production+Redis 부재 시 503."""
    if redis is None:
        if settings.is_production():
            raise HTTPException(status_code=503, detail="OAuth state store unavailable (Redis required in production)")
        logger.warning("OAuth callback: Redis 미설정 — state 검증 skip (non-production only)")
        return
    if not state:
        raise HTTPException(status_code=401, detail="Missing OAuth state (CSRF check)")
    # GETDEL: 값 조회 + 즉시 삭제 (단일 사용). Redis 6.2+ 명령.
    value = await redis.getdel(f"{OAUTH_STATE_KEY_PREFIX}{state}")
    if value is None:
        raise HTTPException(status_code=401, detail="Invalid or expired OAuth state (CSRF check)")


@router.post("/login", response_model=TokenPair)
async def login(
    req: LoginRequest = Body(...),
    use_case: AuthenticateUseCase = Depends(get_authenticate_use_case),
) -> TokenPair:
    try:
        return await use_case.execute(req.code)
    except Exception as exc:
        # Google OAuth 실패(invalid code) 등은 401로 표면화
        raise HTTPException(status_code=401, detail=f"Authentication failed: {exc}") from exc


@router.get("/callback", response_model=TokenPair)
async def callback(
    code: str = Query(..., description="Google OAuth authorization code"),
    state: str | None = Query(None, description="CSRF state (authorize에서 발급)"),
    use_case: AuthenticateUseCase = Depends(get_authenticate_use_case),
    redis: aioredis.Redis | None = Depends(get_redis),
    settings: Settings = Depends(get_settings),
) -> TokenPair:
    """Google OAuth redirect_uri 수신 endpoint. dev/staging에서 브라우저로 직접 호출하여
    JSON으로 access/refresh 토큰을 표시. 프로덕션에서는 프론트엔드가 받아서 cookie/storage에
    저장 후 워크플로 페이지로 redirect하는 것이 일반적.

    state 검증: authorize에서 발급된 토큰을 Redis GETDEL로 소진. 누락/만료 시 401 (CSRF).
    """
    await _consume_oauth_state(state, redis, settings)
    try:
        return await use_case.execute(code)
    except Exception as exc:
        raise HTTPException(status_code=401, detail=f"Authentication failed: {exc}") from exc


@router.post("/refresh", response_model=TokenPair)
async def refresh(
    req: RefreshRequest = Body(...),
    use_case: RefreshTokenUseCase = Depends(get_refresh_token_use_case),
) -> TokenPair:
    return await use_case.execute(req.refresh_token)


@router.get("/me", response_model=PermissionSource)
async def me(
    permission: PermissionSource = Depends(get_permission_source),
) -> PermissionSource:
    return permission
