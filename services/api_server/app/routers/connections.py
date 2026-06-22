"""OAuth connection 관리 라우터 (ADR-0027).

settings 통합 탭 실제 연결 상태 조회(GET) + 연결 버튼(authorize/callback) + 해제(DELETE).
가짜 '연결됨' 하드코딩(settings/page.tsx)을 이 라우터로 대체한다.
"""
from __future__ import annotations

import logging
import secrets
from functools import lru_cache

import redis.asyncio as aioredis
from auth.application.use_cases.complete_connection_use_case import CompleteConnectionUseCase
from auth.application.use_cases.list_connections_use_case import ListConnectionsUseCase
from auth.application.use_cases.revoke_connection_use_case import RevokeConnectionUseCase
from auth.application.use_cases.start_connection_authorize_use_case import StartConnectionAuthorizeUseCase
from auth.domain.entities.user import User
from common_schemas import ConnectionStatus
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

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


class AvailableConnection(BaseModel):
    """연결 가능한 provider 1건 — 카탈로그 사용처(node_count) × auth 연결 메타의 조인 결과."""

    service: str
    name: str
    auth_type: str  # oauth | api_key | connection_string
    available: bool  # 지금 실제 연결 가능(oauth 배선 여부 / 키 입력 상시 가능)
    node_count: int  # 이 provider를 요구하는 카탈로그 노드 수


@lru_cache(maxsize=1)
def _provider_node_counts() -> dict[str, int]:
    """provider → 그 provider를 요구하는 카탈로그 노드 수. 카탈로그는 코드 정의라 프로세스 내 불변 → 1회 산정 후 캐시.

    반환 dict는 공유 캐시 객체이므로 호출 측은 읽기만 한다(변경 금지).
    """
    # lazy import — 카탈로그 모듈은 무거운 어댑터 의존(httpx 등)을 끌어오므로 함수 내부에서 로드.
    from nodes_graph.application.catalog_registry import get_all_node_definitions

    counts: dict[str, int] = {}
    for node in get_all_node_definitions():
        for conn in node.required_connections or []:
            counts[conn] = counts.get(conn, 0) + 1
    return counts


def _connection_redirect_uri(request: Request, settings: Settings, service: str) -> str:
    """connection callback redirect_uri — 정적 `FRONTEND_URL`(https 단일출처) 기준으로 구성.

    `request.url_for`는 Cloud Run 프록시 뒤에서 scheme(https→http)·host가 어긋나(uvicorn이
    `X-Forwarded-Proto`를 신뢰 안 함) google `redirect_uri_mismatch`를 유발한다. 로그인이 정적
    `GOOGLE_REDIRECT_URI` secret을 쓰는 것과 동일한 이유로, connection도 설정값 기준으로 고정한다.
    authorize·callback이 같은 helper를 써 redirect_uri 일치(토큰 교환 통과)를 보장.

    FRONTEND_URL 미설정(로컬 dev = "/")이면 프록시가 없으므로 request 기반으로 폴백.
    """
    base = settings.frontend_url.rstrip("/")
    if base.startswith("http"):
        return f"{base}/api/v1/connections/{service}/callback"
    return str(request.url_for("callback_connection", service=service))


@router.get("", response_model=list[ConnectionStatus])
async def list_connections(
    user: User = Depends(get_current_user),
    use_case: ListConnectionsUseCase = Depends(get_list_connections_use_case),
) -> list[ConnectionStatus]:
    return await use_case.execute(user.user_id)


@router.get("/available", response_model=list[AvailableConnection])
async def available_connections(
    user: User = Depends(get_current_user),
) -> list[AvailableConnection]:
    """연결 가능한 외부 provider 목록 — 하드코딩 대신 카탈로그에서 결정적으로 도출(ADR-0027).

    provider 집합 = nodes_graph 카탈로그의 distinct required_connections(코드 SSOT, 시드 무관 →
    노드 추가 시 자동 반영). provider별 표시명·연결모델은 auth CONNECTION_PROVIDERS가 소유.
    Composition Root가 둘을 조인한다(어느 모듈도 상대 application을 직접 알 필요 없음).
    """
    from auth.application.connection_providers import CONNECTION_PROVIDERS, is_connectable

    counts = _provider_node_counts()  # 캐시된 카탈로그 산정(매 요청 전수 순회 회피)
    result: list[AvailableConnection] = []
    for service in sorted(counts):
        meta = CONNECTION_PROVIDERS.get(service)
        if meta is None:
            # 메타 미정 provider는 노출 안 함(드리프트 가드 테스트가 누락을 잡는다).
            logger.warning("connection provider 메타 누락 — 목록에서 제외: %s", service)
            continue
        result.append(
            AvailableConnection(
                service=service,
                name=meta.name,
                auth_type=meta.auth_type,
                available=is_connectable(service),
                node_count=counts[service],
            )
        )
    return result


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
        redirect_uri = _connection_redirect_uri(request, settings, service)
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
    # authorize와 동일 redirect_uri로 토큰 교환 — google 검증 통과 필수(같은 helper로 일치 보장).
    redirect_uri = _connection_redirect_uri(request, settings, service)
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
