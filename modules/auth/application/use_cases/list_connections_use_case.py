from __future__ import annotations

from uuid import UUID

from common_schemas import ConnectionStatus

from ...domain.ports.oauth_connection_repository import OAuthConnectionRepository


class ListConnectionsUseCase:
    """사용자의 활성(is_active=TRUE) 연결 목록 조회 — settings 통합 탭 실제 상태용 (ADR-0027).

    반환 `ConnectionStatus`는 common_schemas SSOT — api_server 응답·frontend 타입과 단일 정의 공유.
    `display`는 `OAuthConnection.display_name`(026/#422), 미확보 시 None이나 service/connected는 반영.
    """

    def __init__(self, oauth_repo: OAuthConnectionRepository) -> None:
        self._oauth_repo = oauth_repo

    async def execute(self, user_id: UUID) -> list[ConnectionStatus]:
        connections = await self._oauth_repo.list_for_user(user_id)
        return [
            ConnectionStatus(
                service=conn.service,
                connected=True,
                status="connected",
                display=conn.display_name,
            )
            for conn in connections
        ]
