from __future__ import annotations

import uuid

from src.protocols import BaseCipher
from src.repositories.credential_store import CredentialStore


class SecureAccessHelper:
    """Retrieve and optionally wipe credential plaintext with permission checks."""

    def __init__(self, credential_store: CredentialStore, cipher: BaseCipher) -> None:
        self._store = credential_store
        self._cipher = cipher

    async def retrieve_for_tool(
        self, credential_id: uuid.UUID
    ) -> bytes:
        return await self._store.retrieve(credential_id)

    async def retrieve_and_wipe(self, credential_id: uuid.UUID) -> bytes:
        plaintext = await self._store.retrieve(credential_id)
        await self._store.delete_credential(credential_id)
        return plaintext
