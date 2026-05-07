from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.credential import CredentialModel
from src.protocols import BaseCipher
from src.repositories.base import BaseRepository


class CredentialStore(BaseRepository[CredentialModel]):
    """H-2 contract: cipher DI for encrypt/decrypt credential data."""

    def __init__(self, session: AsyncSession, cipher: BaseCipher) -> None:
        super().__init__(session)
        self._cipher = cipher

    async def store(
        self,
        user_id: uuid.UUID,
        name: str,
        credential_kind: str,
        plaintext: bytes,
    ) -> uuid.UUID:
        encrypted = self._cipher.encrypt(plaintext)
        instance = await self.create(
            user_id=user_id,
            name=name,
            credential_kind=credential_kind,
            encrypted_data=encrypted,
        )
        return instance.id

    async def retrieve(self, credential_id: uuid.UUID) -> bytes:
        instance = await self.get_or_raise(credential_id)
        return self._cipher.decrypt(instance.encrypted_data)

    async def delete_credential(self, credential_id: uuid.UUID) -> bool:
        return await self.delete(credential_id)
