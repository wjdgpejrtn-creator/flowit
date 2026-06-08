"""OAuth connection 관리 라우터 (ADR-0027).

settings 통합 탭의 실제 연결 상태 조회(GET) + 연결 버튼(authorize/callback) + 해제(DELETE).
가짜 '연결됨' 하드코딩(settings/page.tsx)을 이 라우터로 대체한다.
"""
from __future__ import annotations

import logging
import secrets

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from auth.application.use_cases.complete_connection_use_case import CompleteConnectionUseCase
from auth.application.use_cases.list_connections_use_case import ListConnectionsUseCase
from auth.application.use_cases.revoke_connection_use_case import RevokeConnectionUseCase
from auth.application.use_cases.start_connection_authorize_use_case import StartConnectionAuthorizeUseCase
from auth.domain.entities.user import User
from auth.domain.ports.cipher_port import CipherPort
from auth.domain.ports.credential_repository import CredentialRepository
from auth.domain.ports.oauth_client_port import OAuthClientPort
from auth.domain.ports.oauth_connection_repository import OAuthConnectionRepository

from ..config import Settings
from ..dependencies.auth import (
    get_cipher,
    get_credential_repository,
    get_google_oauth,
    get_oauth_repository,
)
from ..dependencies.clients import get_redis
from ..dependencies.permission import get_current_user
from ..dependencies.settings import get_settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/connections", tags=["connections"])

# connection authorize CSRF state — 로그인 state(`oauth_state:`)와 분리.
CONN_STATE_PREFIX = "conn_oauth_state:"
CONN_STATE_TTL_SECONDS = 600


class ConnectionResponse(BaseModel):
    """ADR-0027 응답 계약. display=google 이메일 / slack workspace (미확보 시 null)."""

    service: str
    display: str | None
    connected: bool
    status: str  # "connected" | "expired"


class AuthorizeConnectionResponse(BaseModel):
    authorization_url: str
    state: str


@router.get("", response_model=list[ConnectionResponse])
async def list_connections(
    user: User = Depends(get_current_user),
    oauth_repo: OAuthConnectionRepository = Depends(get_oauth_repository),
) -> list[ConnectionResponse]:
    statuses = await ListConnectionsUseCase(oauth_repo).execute(user.user_id)
    return [
        ConnectionResponse(service=s.service, display=s.display, connected=s.connected, status=s.status)
        for s in statuses
    ]


@router.get("/{service}/authorize", response_model=AuthorizeConnectionResponse)
async def authorize_connection(
    service: str,
    user: User = Depends(get_current_user),
    google_oauth: OAuthClientPort = Depends(get_google_oauth),
    redis: aioredis.Redis | None = Depends(get_redis),
    settings: Settings = Depends(get_settings),
) -> AuthorizeConnectionResponse:
    """connection authorize URL 발급 — 프론트가 이 URL로 리다이렉트해 동의 화면을 띄운다."""
    try:
        state = secrets.token_urlsafe(24)
        url = StartConnectionAuthorizeUseCase(google_oauth).build_authorization_url(service, state)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if redis is not None:
        await redis.setex(f"{CONN_STATE_PREFIX}{state}", CONN_STATE_TTL_SECONDS, "1")
    elif settings.is_production():
        raise HTTPException(status_code=503, detail="OAuth state store unavailable (Redis required in production)")
    else:
        logger.warning("connection authorize: Redis 미설정 — state CSRF 검증 비활성 (non-production only)")
    return AuthorizeConnectionResponse(authorization_url=url, state=state)


async def _consume_conn_state(state: str | None, redis: aioredis.Redis | None, settings: Settings) -> None:
    """connection callback state 검증 + 일회 소진 (GETDEL). invalid/expired 시 401."""
    if redis is None:
        if settings.is_production():
            raise HTTPException(status_code=503, detail="OAuth state store unavailable (Redis required in production)")
        return
    if not state:
        raise HTTPException(status_code=401, detail="Missing OAuth state (CSRF check)")
    value = await redis.getdel(f"{CONN_STATE_PREFIX}{state}")
    if value is None:
        raise HTTPException(status_code=401, detail="Invalid or expired OAuth state (CSRF check)")


@router.get("/{service}/callback")
async def callback_connection(
    service: str,
    code: str = Query(..., description="OAuth authorization code"),
    state: str | None = Query(None, description="CSRF state (authorize에서 발급)"),
    user: User = Depends(get_current_user),
    oauth_repo: OAuthConnectionRepository = Depends(get_oauth_repository),
    credential_repo: CredentialRepository = Depends(get_credential_repository),
    cipher: CipherPort = Depends(get_cipher),
    google_oauth: OAuthClientPort = Depends(get_google_oauth),
    redis: aioredis.Redis | None = Depends(get_redis),
    settings: Settings = Depends(get_settings),
) -> RedirectResponse:
    """OAuth redirect_uri 수신 — code 교환·저장 후 settings로 복귀(쿼리로 성공/실패 시그널)."""
    await _consume_conn_state(state, redis, settings)
    try:
        await CompleteConnectionUseCase(oauth_repo, credential_repo, cipher, google_oauth).execute(
            user.user_id, service, code
        )
    except Exception as exc:
        logger.warning("connection callback 실패 (%s): %s", service, exc)
        return RedirectResponse(url=f"{settings.frontend_url}/settings?error=connect_failed", status_code=302)
    return RedirectResponse(url=f"{settings.frontend_url}/settings?connected={service}", status_code=302)


@router.delete("/{service}")
async def revoke_connection(
    service: str,
    user: User = Depends(get_current_user),
    oauth_repo: OAuthConnectionRepository = Depends(get_oauth_repository),
) -> dict:
    revoked = await RevokeConnectionUseCase(oauth_repo).execute(user.user_id, service)
    return {"service": service, "revoked": revoked}
