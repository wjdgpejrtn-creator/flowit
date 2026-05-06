from __future__ import annotations

from uuid import UUID

from common_schemas import PlaintextCredential

from ...domain.services.credential_injection import CredentialInjectionService


class InjectCredentialUseCase:
    def __init__(self, service: CredentialInjectionService) -> None:
        self._service = service

    async def execute(self, credential_id: UUID) -> PlaintextCredential:
        credential = await self._service.inject(credential_id)
        return credential
