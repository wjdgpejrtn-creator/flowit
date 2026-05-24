from __future__ import annotations

import logging
import secrets
from uuid import UUID

import redis.asyncio as aioredis
from auth.adapters.jwt_adapter import JWTAdapter
from auth.adapters.oauth.google_oauth_client import GoogleOAuthClient
from auth.application.use_cases.authenticate_use_case import AuthenticateUseCase
from auth.application.use_cases.grant_user_role_use_case import GrantUserRoleUseCase
from auth.application.use_cases.refresh_token_use_case import RefreshTokenUseCase
from auth.domain.entities.user import UserRole
from auth.domain.ports.session_repository import SessionRepository
from common_schemas import PermissionSource
from common_schemas.exceptions import AuthorizationError
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel

from app.config import Settings
from app.cookies import ACCESS_COOKIE, REFRESH_COOKIE, clear_auth_cookies, set_auth_cookies
from app.dependencies.auth import (
    get_authenticate_use_case,
    get_google_oauth,
    get_grant_user_role_use_case,
    get_jwt_adapter,
    get_refresh_token_use_case,
    get_session_repository,
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


class AuthorizeResponse(BaseModel):
    authorization_url: str
    state: str


class RefreshResponse(BaseModel):
    expires_in: int


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


@router.get("/callback")
async def callback(
    code: str = Query(..., description="Google OAuth authorization code"),
    state: str | None = Query(None, description="CSRF state (authorize에서 발급)"),
    use_case: AuthenticateUseCase = Depends(get_authenticate_use_case),
    redis: aioredis.Redis | None = Depends(get_redis),
    settings: Settings = Depends(get_settings),
) -> RedirectResponse:
    """Google OAuth redirect_uri 수신 endpoint (ADR-0021 A안).

    code를 토큰으로 교환한 뒤 access/refresh를 HttpOnly 쿠키로 굽고 frontend(`FRONTEND_URL`)로
    302 redirect한다. 토큰이 브라우저 JS에 노출되지 않으므로 XSS 내성을 갖는다.

    state 검증: authorize에서 발급된 토큰을 Redis GETDEL로 소진. 누락/만료 시 401 (CSRF).
    """
    await _consume_oauth_state(state, redis, settings)
    try:
        tokens = await use_case.execute(code)
    except Exception as exc:
        raise HTTPException(status_code=401, detail=f"Authentication failed: {exc}") from exc

    response = RedirectResponse(url=settings.frontend_url, status_code=302)
    set_auth_cookies(response, tokens, settings)
    return response


@router.post("/refresh", response_model=RefreshResponse)
async def refresh(
    request: Request,
    use_case: RefreshTokenUseCase = Depends(get_refresh_token_use_case),
    settings: Settings = Depends(get_settings),
) -> Response:
    """`refresh_token` 쿠키로 새 토큰 쌍을 발급하고 쿠키를 재set한다 (ADR-0021).

    토큰은 응답 본문에 싣지 않는다 — 본문은 frontend가 다음 갱신을 예약할 수 있도록 `expires_in`만 반환.
    """
    refresh_token = request.cookies.get(REFRESH_COOKIE)
    if not refresh_token:
        raise HTTPException(status_code=401, detail="Missing refresh token cookie")

    try:
        tokens = await use_case.execute(refresh_token)
    except AuthorizationError as exc:
        # 만료·무효 refresh 토큰 / 만료된 session = 재인증이 필요한 정상 케이스 → 401.
        # /callback과 달리 외부 호출이 없으므로 AuthorizationError만 잡고, 그 외 예외(DB 장애 등)는
        # 500으로 전파해 모니터링에 실제 장애가 드러나도록 둔다.
        raise HTTPException(status_code=401, detail="Refresh token invalid or expired") from exc

    response = JSONResponse({"expires_in": tokens.expires_in})
    set_auth_cookies(response, tokens, settings)
    return response


@router.post("/logout", status_code=204)
async def logout(
    request: Request,
    session_repo: SessionRepository = Depends(get_session_repository),
    jwt_adapter: JWTAdapter = Depends(get_jwt_adapter),
    settings: Settings = Depends(get_settings),
) -> Response:
    """인증 쿠키를 제거하고 서버측 세션을 revoke한다 (ADR-0021).

    refresh_token(없으면 access_token) 쿠키에서 session_hash를 복원해 세션을 revoke한다.
    토큰이 만료/손상돼도 로그아웃 자체는 성공해야 하므로 revoke는 best-effort.
    """
    token = request.cookies.get(REFRESH_COOKIE) or request.cookies.get(ACCESS_COOKIE)
    if token:
        try:
            payload = jwt_adapter.decode(token)
            session_hash = payload.get("session_hash")
            if session_hash:
                session = await session_repo.find_by_hash(session_hash)
                if session is not None:
                    await session_repo.revoke(session.session_id)
        except Exception:
            # 만료/손상 토큰 — 서버측 revoke 불가하나 쿠키 정리는 계속 진행
            logger.info("logout: 세션 revoke 생략 (토큰 디코드 실패) — 쿠키만 정리")

    response = Response(status_code=204)
    clear_auth_cookies(response, settings)
    return response


@router.get("/me", response_model=PermissionSource)
async def me(
    permission: PermissionSource = Depends(get_permission_source),
) -> PermissionSource:
    return permission


class GrantRoleRequest(BaseModel):
    role: UserRole
    department_id: UUID | None = None


class GrantRoleResponse(BaseModel):
    user_id: UUID
    role: UserRole
    department_id: UUID | None


@router.put("/users/{user_id}/role", response_model=GrantRoleResponse)
async def grant_user_role(
    user_id: UUID,
    body: GrantRoleRequest,
    actor: PermissionSource = Depends(get_permission_source),
    use_case: GrantUserRoleUseCase = Depends(get_grant_user_role_use_case),
) -> GrantRoleResponse:
    """Admin이 다른 사용자의 역할/소속 팀(department)을 변경한다 (스킬 마켓플레이스 RBAC).

    인가는 use case에서 검증 — actor.role != 'Admin'이면 403(E-PERM-001).
    team_manager 부여 시 department_id 필수(없으면 400). 도메인 예외는 error_handler가 HTTP로 매핑.
    """
    user = await use_case.execute(
        actor=actor,
        target_user_id=user_id,
        role=body.role,
        department_id=body.department_id,
    )
    return GrantRoleResponse(
        user_id=user.user_id,
        role=user.role,
        department_id=user.department_id,
    )
