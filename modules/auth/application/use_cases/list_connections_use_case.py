from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from ...domain.ports.oauth_connection_repository import OAuthConnectionRepository


@dataclass(frozen=True)
class ConnectionStatus:
    """settings GET /connections 응답 1행 (ADR-0027 응답 계약).

    display는 026 마이그레이션(`account_id`/`display_name`) 후 채운다 — google=email / slack=workspace.
    그 전에도 service/connected/status로 "실제 연결 여부"는 반영된다(가짜 '연결됨' 제거).
    """

    service: str
    connected: bool
    status: str  # "connected" | "expired" (expired는 ① 토큰 refresh 구현 후)
    display: str | None


class ListConnectionsUseCase:
    """사용자의 활성(is_active=TRUE) 연결 목록 조회 — settings 통합 탭 실제 상태용 (ADR-0027)."""

    def __init__(self, oauth_repo: OAuthConnectionRepository) -> None:
        self._oauth_repo = oauth_repo

    async def execute(self, user_id: UUID) -> list[ConnectionStatus]:
        connections = await self._oauth_repo.list_for_user(user_id)
        return [
            ConnectionStatus(
                service=conn.service,
                connected=True,
                status="connected",
                display=conn.display_name,  # 026(#422): google=email / slack=workspace, 미확보 시 None
            )
            for conn in connections
        ]
