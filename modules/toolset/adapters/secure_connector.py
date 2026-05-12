from __future__ import annotations

import json

import httpx

from auth.domain.services import CredentialInjectionService
from common_schemas.security import PlaintextCredential

from ..domain.ports.secure_connector_port import SecureConnectorPort
from ..domain.value_objects.connector_response import ConnectorResponse


class SecureConnectorAdapter(SecureConnectorPort):
    """httpx 기반 SecureConnectorPort 구현체.

    credential.value를 Authorization Bearer 헤더로 주입한다.
    kwargs: method, headers, body, params, timeout
    """

    def __init__(self, credential_injection_svc: CredentialInjectionService) -> None:
        self._credential_svc = credential_injection_svc

    async def connect(
        self,
        endpoint: str,
        credentials: PlaintextCredential,
        **kwargs,
    ) -> ConnectorResponse:
        method: str = kwargs.get("method", "GET").upper()
        extra_headers: dict = kwargs.get("headers") or {}
        body = kwargs.get("body")
        params = kwargs.get("params")
        timeout = kwargs.get("timeout", 30)

        headers = {**extra_headers}
        if credentials and credentials.value:
            headers["Authorization"] = f"Bearer {credentials.value}"

        content = json.dumps(body).encode() if body is not None else None

        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.request(
                method=method,
                url=endpoint,
                headers=headers,
                content=content,
                params=params,
            )

        return ConnectorResponse(
            status_code=response.status_code,
            body=response.content,
            headers=dict(response.headers),
        )
