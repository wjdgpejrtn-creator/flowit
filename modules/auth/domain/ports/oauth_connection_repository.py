from abc import ABC, abstractmethod
from uuid import UUID

from ..entities.oauth_connection import OAuthConnection


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
    async def update_tokens(self, credential_id: UUID, new_tokens: dict) -> None: ...

    @abstractmethod
    async def revoke(self, credential_id: UUID) -> None: ...
