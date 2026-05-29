from __future__ import annotations

from abc import ABC, abstractmethod

from common_schemas.security import PlaintextCredential

from ..value_objects.connector_response import ConnectorResponse


class SecureConnectorPort(ABC):
    """외부 엔드포인트에 자격증명을 주입해 HTTP 요청을 수행하는 Port.

    구현체: adapters/secure_connector.py (auth.CredentialInjectionService 연동)
    adapter에서 httpx.Response → ConnectorResponse 변환 책임.
    """

    @abstractmethod
    async def connect(
        self,
        endpoint: str,
        credentials: PlaintextCredential,
        **kwargs,
    ) -> ConnectorResponse: ...
