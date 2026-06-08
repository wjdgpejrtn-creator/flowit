"""OAuth connection 관리 라우터 (ADR-0027).

settings 통합 탭 실제 연결 상태 조회(GET) + 연결 버튼(authorize/callback) + 해제(DELETE).
가짜 '연결됨' 하드코딩(settings/page.tsx)을 이 라우터로 대체한다.
"""
from __future__ import annotations

import logging
import secrets

import redis.asyncio as aioredis
from common_schemas import ConnectionStatus
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from auth.application.use_cases.complete_connection_use_case import CompleteConnectionUseCase
from auth.application.use_cases.list_connections_use_case import ListConnectionsUseCase
from auth.application.use_cases.revoke_connection_use_case import RevokeConnectionUseCase
from auth.application.use_cases.start_connection_authorize_use_case import StartConnectionAuthorizeUseCase
from auth.domain.entities.user import User

from ..config import Settings
from ..dependencies.clients import get_redis
from ..dependencies.connections import (
    get_complete_connection_use_case,
    get_list_connections_use_case,
    get_revoke_connection_use_case,
    get_start_connection_use_case,
)
from ..dependencies.permission import get_current_user
from ..dependencies.settings import get_settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/connections", tags=["connections"])

# connection authorize CSRF state — 로그인 state(`oauth_state:`)와 분리.
CONN_STATE_PREFIX = "conn_oauth_state:"
CONN_STATE_TTL_SECONDS = 600


class AuthorizeConnectionResponse(BaseModel):
    authorization_url: str
    state: str


@router.get("", response_model=list[ConnectionStatus])
async def list_connections(
    user: User = Depends(get_current_user),
    use_case: ListConnectionsUseCase = Depends(get_list_connections_use_case),
) -> list[ConnectionStatus]:
    return await use_case.execute(user.user_id)


@router.get("/{service}/authorize", response_model=AuthorizeConnectionResponse)
async def authorize_connection(
    request: Request,
    service: str,
    user: User = Depends(get_current_user),
    use_case: StartConnectionAuthorizeUseCase = Depends(get_start_connection_use_case),
    redis: aioredis.Redis | None = Depends(get_redis),
    settings: Settings = Depends(get_settings),
) -> AuthorizeConnectionResponse:
    """connection authorize URL 발급 — 프론트가 이 URL로 리다이렉트해 동의 화면을 띄운다."""
    try:
        state = secrets.token_urlsafe(24)
        # redirect_uri = 이 connection의 callback 경로 — 로그인 callback과 분리(redirect mismatch 방지).
        redirect_uri = str(request.url_for("callback_connection", service=service))
        url = use_case.build_authorization_url(service, state, redirect_uri)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if redis is not None:
        # state → user_id 바인딩(connection-fixation CSRF 방어, 조장 MED) — callback이 동일 user 확인.
        await redis.setex(f"{CONN_STATE_PREFIX}{state}", CONN_STATE_TTL_SECONDS, str(user.user_id))
    elif settings.is_production():
        raise HTTPException(status_code=503, detail="OAuth state store unavailable (Redis required in production)")
    else:
        logger.warning("connection authorize: Redis 미설정 — state CSRF 검증 비활성 (non-production only)")
    return AuthorizeConnectionResponse(authorization_url=url, state=state)


async def _consume_conn_state(
    state: str | None, redis: aioredis.Redis | None, settings: Settings, expected_user_id: object
) -> None:
    """connection callback state 검증 + 일회 소진(GETDEL) + **user 바인딩 검증**(CSRF, 조장 MED).

    authorize가 state→user_id를 저장 → callback이 현재 인증 user와 일치 확인(connection-fixation 방어).
    """
    if redis is None:
        if settings.is_production():
            raise HTTPException(status_code=503, detail="OAuth state store unavailable (Redis required in production)")
        return
    if not state:
        raise HTTPException(status_code=401, detail="Missing OAuth state (CSRF check)")
    value = await redis.getdel(f"{CONN_STATE_PREFIX}{state}")
    if value is None:
        raise HTTPException(status_code=401, detail="Invalid or expired OAuth state (CSRF check)")
    bound = value.decode() if isinstance(value, (bytes, bytearray)) else value
    if bound != str(expected_user_id):
        raise HTTPException(status_code=401, detail="OAuth state user mismatch (CSRF check)")


@router.get("/{service}/callback")
async def callback_connection(
    request: Request,
    service: str,
    code: str = Query(..., description="OAuth authorization code"),
    state: str | None = Query(None, description="CSRF state (authorize에서 발급)"),
    user: User = Depends(get_current_user),
    use_case: CompleteConnectionUseCase = Depends(get_complete_connection_use_case),
    redis: aioredis.Redis | None = Depends(get_redis),
    settings: Settings = Depends(get_settings),
) -> RedirectResponse:
    """OAuth redirect_uri 수신 — code 교환·저장 후 settings로 복귀(쿼리로 성공/실패 시그널)."""
    await _consume_conn_state(state, redis, settings, user.user_id)
    # authorize와 동일 redirect_uri로 토큰 교환 — google 검증 통과 필수.
    redirect_uri = str(request.url_for("callback_connection", service=service))
    try:
        await use_case.execute(user.user_id, service, code, redirect_uri)
    except Exception as exc:
        logger.warning("connection callback 실패 (%s): %s", service, exc)
        return RedirectResponse(url=f"{settings.frontend_url}/settings?error=connect_failed", status_code=302)
    return RedirectResponse(url=f"{settings.frontend_url}/settings?connected={service}", status_code=302)


@router.delete("/{service}")
async def revoke_connection(
    service: str,
    user: User = Depends(get_current_user),
    use_case: RevokeConnectionUseCase = Depends(get_revoke_connection_use_case),
) -> dict:
    revoked = await use_case.execute(user.user_id, service)
    return {"service": service, "revoked": revoked}
