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
    async def update_tokens(self, credential_id: UUID, new_tokens: dict) -> None: ...

    @abstractmethod
    async def revoke(self, credential_id: UUID) -> None: ...
