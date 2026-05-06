from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional
from uuid import UUID

from ..entities.oauth_connection import OAuthConnection


class OAuthConnectionRepository(ABC):
    @abstractmethod
    async def create(
        self,
        user_id: UUID,
        service: str,
        encrypted_access_token: bytes,
        encrypted_refresh_token: bytes,
        scopes: list[str],
        token_expires_at: Optional[datetime] = None,
    ) -> OAuthConnection: ...

    @abstractmethod
    async def get_by_credential_id(self, credential_id: UUID) -> OAuthConnection: ...

    @abstractmethod
    async def get_active_for_user(self, user_id: UUID, service: str) -> OAuthConnection: ...

    @abstractmethod
    async def update_tokens(
        self,
        credential_id: UUID,
        encrypted_access_token: bytes,
        encrypted_refresh_token: bytes,
    ) -> None: ...

    @abstractmethod
    async def revoke(self, credential_id: UUID) -> None: ...
