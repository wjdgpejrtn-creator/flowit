from __future__ import annotations

from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from common_schemas.security import PlaintextCredential


class SecureConnectorPort(ABC):
    """
    자격증명 획득/해제 Port.
    구현체: adapters/secure_connector.py (CredentialInjectionService 연동)

    acquire ~ release 사이에만 평문 메모리 보유.
    ExecuteToolUseCase.execute() finally 블록에서 반드시 release 호출.
    """

    @abstractmethod
    async def acquire_credential(
        self,
        credential_id: str,
        service: str,
    ) -> PlaintextCredential:
        """Raises: CredentialError — 자격증명 미존재 또는 복호화 실패"""
        ...

    @abstractmethod
    async def release_credential(self, credential_id: str) -> None:
        """메모리에서 credential 제거. best-effort — 실패 시 예외 없음."""
        ...

    @asynccontextmanager
    async def credential_context(
        self,
        credential_id: str,
        service: str,
    ) -> AsyncGenerator[PlaintextCredential, None]:
        credential = await self.acquire_credential(credential_id, service)
        try:
            yield credential
        finally:
            credential.wipe()
            await self.release_credential(credential_id)
