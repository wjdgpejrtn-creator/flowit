from __future__ import annotations

from common_schemas import PermissionSource
from common_schemas.exceptions import AuthorizationError

from ...domain.ports.oauth_connection_repository import OAuthConnectionRepository
from ...domain.value_objects.connection_audit_entry import ConnectionAuditEntry


class ListConnectionAuditUseCase:
    """관리자 자격증명 감사 — 전사 OAuth connection을 소유자와 함께 나열 (REQ-002/003).

    관리자 화면(`/admin/credentials`) 백엔드. `GrantUserRoleUseCase`와 동일한 Admin 게이트:
    actor.role != 'Admin'이면 `AuthorizationError`(E-PERM-001, fail-closed). 통과 시 repo의
    전사 감사 목록(소유자 email/name/department join, 토큰 제외)을 그대로 반환한다.
    """

    def __init__(self, oauth_repo: OAuthConnectionRepository) -> None:
        self._oauth_repo = oauth_repo

    async def execute(
        self,
        *,
        actor: PermissionSource,
        limit: int = 200,
        offset: int = 0,
    ) -> list[ConnectionAuditEntry]:
        if actor.role != "Admin":
            raise AuthorizationError(
                "Only Admin can audit credentials", code="E-PERM-001"
            )
        return await self._oauth_repo.list_connection_audit(limit=limit, offset=offset)
