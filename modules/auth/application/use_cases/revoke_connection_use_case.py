from __future__ import annotations

from uuid import UUID

from ...domain.ports.oauth_connection_repository import OAuthConnectionRepository


class RevokeConnectionUseCase:
    """connection 해제 — 활성 연결을 is_active=FALSE로 (ADR-0027 DELETE /connections/{service})."""

    def __init__(self, oauth_repo: OAuthConnectionRepository) -> None:
        self._oauth_repo = oauth_repo

    async def execute(self, user_id: UUID, service: str) -> bool:
        """해제 성공 시 True, 활성 연결이 없으면 False(멱등)."""
        conn = await self._oauth_repo.get_active_for_user(user_id, service)
        if conn is None:
            return False
        await self._oauth_repo.revoke(conn.credential_id)
        return True
