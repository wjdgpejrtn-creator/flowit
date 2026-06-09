from abc import ABC, abstractmethod
from uuid import UUID

from ..entities.oauth_connection import OAuthConnection
from ..value_objects.connection_audit_entry import ConnectionAuditEntry


class OAuthConnectionRepository(ABC):
    @abstractmethod
    async def create(self, user_id: UUID, service: str, tokens: dict) -> OAuthConnection: ...

    @abstractmethod
    async def get_by_credential_id(self, credential_id: UUID) -> OAuthConnection | None: ...

    @abstractmethod
    async def get_active_for_user(self, user_id: UUID, service: str) -> OAuthConnection | None: ...

    @abstractmethod
    async def list_for_user(self, user_id: UUID) -> list[OAuthConnection]:
        """사용자의 활성(is_active=TRUE) 연결 전체 목록 (settings GET /connections용, ADR-0027).

        `get_active_for_user`(단일 service)와 달리 모든 service의 active 연결을 반환한다.
        """
        ...

    @abstractmethod
    async def list_connection_audit(
        self, limit: int = 200, offset: int = 0
    ) -> list[ConnectionAuditEntry]:
        """전사 OAuth connection을 소유자(email/name/department)와 함께 나열 — 관리자 감사용.

        `list_for_user`(user 범위, settings)와 달리 owner 필터가 없다 — 관리자가 전 사용자의
        connection을 소유자 무관하게 모아 본다(`/admin/credentials`). 인가(Admin only)는 use case
        (`ListConnectionAuditUseCase`)가 enforce한다. is_active 무관(해지된 connection도 감사 대상).
        구현은 users JOIN으로 소유자 식별 합성, 토큰은 제외. 정렬은 구현에서 `connected_at DESC`.
        """
        ...

    @abstractmethod
    async def update_tokens(self, credential_id: UUID, new_tokens: dict) -> None: ...

    @abstractmethod
    async def revoke(self, credential_id: UUID) -> None: ...
