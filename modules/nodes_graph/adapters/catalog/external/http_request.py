from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid5

import httpx
from common_schemas import NodeContext
from common_schemas.enums import RiskLevel

from ....domain.catalog._catalog_ns import _CATALOG_NS
from ....domain.entities.base_node import BaseNode
from ....domain.entities.node_definition import NodeDefinition
from ....domain.entities.node_metadata import NodeMetadata
from ._url_guard import validate_outbound_url

_NODE_TYPE = "http_request"
_NODE_ID = uuid5(_CATALOG_NS, _NODE_TYPE)


@dataclass
class HttpRequestInput:
    url: str
    method: str = "GET"  # GET | POST | PUT | DELETE | PATCH
    headers: dict[str, str] = field(default_factory=dict)
    body: dict[str, Any] | None = None
    timeout: float = 30.0


@dataclass
class HttpRequestOutput:
    status_code: int
    headers: dict[str, str]
    body: Any
    text: str
    ok: bool


class HttpRequestNode(BaseNode[HttpRequestInput, HttpRequestOutput]):
    metadata = NodeMetadata(
        node_id=_NODE_ID,
        name="HTTP 요청",
        category="integration",
        risk_level=RiskLevel.HIGH,
        is_mvp=True,
    )
    input_schema = HttpRequestInput
    output_schema = HttpRequestOutput

    async def process(self, input: HttpRequestInput, context: NodeContext) -> HttpRequestOutput:
        await validate_outbound_url(input.url)
        async with httpx.AsyncClient(timeout=input.timeout) as client:
            response = await client.request(
                method=input.method.upper(),
                url=input.url,
                headers=input.headers,
                json=input.body,
            )
        try:
            body: Any = response.json()
        except Exception:
            body = response.text
        return HttpRequestOutput(
            status_code=response.status_code,
            headers=dict(response.headers),
            body=body,
            text=response.text,
            ok=response.is_success,
        )


def get_node_definition() -> NodeDefinition:
    return NodeDefinition(
        node_id=_NODE_ID,
        node_type=_NODE_TYPE,
        name="HTTP 요청",
        category="integration",
        version="1.0.0",
        input_schema={
            "type": "object",
            "properties": {
                "url": {"type": "string", "format": "uri", "description": "호출할 API의 전체 URL"},
                "method": {
                    "type": "string",
                    "enum": ["GET", "POST", "PUT", "DELETE", "PATCH"],
                    "default": "GET",
                    "description": "HTTP 메서드(GET/POST/PUT/DELETE/PATCH). 기본값 GET",
                },
                "headers": {"type": "object", "description": "요청 HTTP 헤더 객체"},
                "body": {"type": "object", "description": "요청 본문(JSON)"},
                "timeout": {"type": "number", "default": 30.0, "description": "응답 대기 제한 시간(초). 기본값 30"},
            },
            "required": ["url"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "status_code": {"type": "integer"},
                "headers": {"type": "object"},
                "body": {},
                "text": {"type": "string"},
                "ok": {"type": "boolean"},
            },
        },
        parameter_schema={},
        risk_level=RiskLevel.HIGH,
        required_connections=[],
        description="외부 HTTP API 호출 (GET/POST/PUT/DELETE/PATCH). httpx 비동기 클라이언트 사용",
        is_mvp=True,
        service_type=None,
    )
