from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID


class CredentialProviderPort(ABC):

    @abstractmethod
    def get_credential(self, credential_id: UUID, user_id: UUID) -> dict[str, str]:
        ...
