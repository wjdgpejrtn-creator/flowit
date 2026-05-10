from __future__ import annotations

import logging
from typing import Protocol
from uuid import UUID

from ..domain.ports.credential_provider_port import CredentialProviderPort

logger = logging.getLogger(__name__)


class CredentialStoreProtocol(Protocol):
    def decrypt(self, credential_id: UUID, user_id: UUID) -> dict[str, str]: ...


class VaultCredentialProvider(CredentialProviderPort):

    def __init__(self, credential_store: CredentialStoreProtocol) -> None:
        self._store = credential_store

    def get_credential(self, credential_id: UUID, user_id: UUID) -> dict[str, str]:
        logger.debug(
            "Resolving credential=%s for user=%s", credential_id, user_id
        )
        return self._store.decrypt(credential_id, user_id)
