from __future__ import annotations

from abc import ABC, abstractmethod

import httpx
from common_schemas.security import PlaintextCredential


class SecureConnectorPort(ABC):
    """외부 엔드포인트에 자격증명을 주입해 HTTP 요청을 수행하는 Port.

    구현체: adapters/secure_connector.py (auth.CredentialInjectionService 연동)
    """

    @abstractmethod
    async def connect(
        self,
        endpoint: str,
        credentials: PlaintextCredential,
        **kwargs,
    ) -> httpx.Response: ...
