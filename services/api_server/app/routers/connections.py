"""OAuth connection 관리 라우터 (ADR-0027).

settings 통합 탭의 "실제 연결 상태" 조회. 가짜 '연결됨' 하드코딩(settings/page.tsx)을
이 엔드포인트로 대체한다. authorize/callback/DELETE는 후속.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from auth.application.use_cases.list_connections_use_case import ListConnectionsUseCase
from auth.domain.entities.user import User
from auth.domain.ports.oauth_connection_repository import OAuthConnectionRepository

from ..dependencies.auth import get_oauth_repository
from ..dependencies.permission import get_current_user

router = APIRouter(prefix="/api/v1/connections", tags=["connections"])


class ConnectionResponse(BaseModel):
    """ADR-0027 응답 계약. display=google 이메일 / slack workspace (미확보 시 null)."""

    service: str
    display: str | None
    connected: bool
    status: str  # "connected" | "expired"


@router.get("", response_model=list[ConnectionResponse])
async def list_connections(
    user: User = Depends(get_current_user),
    oauth_repo: OAuthConnectionRepository = Depends(get_oauth_repository),
) -> list[ConnectionResponse]:
    statuses = await ListConnectionsUseCase(oauth_repo).execute(user.user_id)
    return [
        ConnectionResponse(
            service=s.service,
            display=s.display,
            connected=s.connected,
            status=s.status,
        )
        for s in statuses
    ]
