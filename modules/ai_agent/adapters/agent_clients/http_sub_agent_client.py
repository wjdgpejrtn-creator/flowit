from __future__ import annotations

import json
from typing import Any, AsyncIterator

import httpx

from common_schemas.agent_protocol import AgentProtocolRequest, AgentProtocolResponse

from ...domain.ports.sub_agent_client import SubAgentClient

_ROUTE_PATH = "/v1/agent/route"
# Modal cold start(60s) + 스트리밍 처리 여유
_DEFAULT_TIMEOUT = 120.0


class HTTPSubAgentClient(SubAgentClient):
    """SubAgentClient 구현 — httpx SSE 스트리밍으로 sub-agent Modal app 호출.

    VPC 내부 통신 전용. 각 sub-agent(composer/skills_builder/personalization)에
    대해 별도 인스턴스를 생성하고 base_url만 다르게 주입한다.
    """

    def __init__(self, base_url: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT)

    async def send(
        self, request: AgentProtocolRequest
    ) -> AsyncIterator[AgentProtocolResponse]:
        url = f"{self._base_url}{_ROUTE_PATH}"
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if request.trace_id:
            headers["X-Trace-Id"] = request.trace_id

        async with self._client.stream(
            "POST",
            url,
            content=request.model_dump_json(),
            headers=headers,
        ) as response:
            response.raise_for_status()
            async for raw_line in response.aiter_lines():
                if not raw_line:
                    continue
                line = raw_line.strip()
                if not line.startswith("data: "):
                    continue
                payload: dict[str, Any] = json.loads(line[6:])
                yield AgentProtocolResponse.model_validate(payload)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> HTTPSubAgentClient:
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.aclose()
