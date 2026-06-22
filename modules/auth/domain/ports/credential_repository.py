from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any
from uuid import UUID

from ..entities.credential import Credential, CredentialKind


class CredentialRepository(ABC):
    """Credential 저장/조회 Port. 구현체는 modules/storage/repositories/."""

    @abstractmethod
    async def create(
        self,
        user_id: UUID,
        name: str,
        credential_kind: CredentialKind,
        encrypted_data: bytes,
        metadata: dict[str, Any] | None = None,
    ) -> Credential: ...

    @abstractmethod
    async def get_by_id(self, credential_id: UUID) -> Credential | None: ...

    @abstractmethod
    async def update_data(self, credential_id: UUID, encrypted_data: bytes) -> None: ...
