from __future__ import annotations

import json
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

_NODE_TYPE = "rest_api"
_NODE_ID = uuid5(_CATALOG_NS, _NODE_TYPE)
_MAX_TIMEOUT_SECONDS = 300  # input_schema의 timeout_seconds maximum과 정합


@dataclass
class RestApiInput:
    base_url: str
    path: str = ""
    method: str = "GET"  # GET | POST | PUT | PATCH | DELETE
    query_params: dict[str, Any] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)
    body: dict[str, Any] | None = None
    timeout_seconds: int = 30


@dataclass
class RestApiOutput:
    status_code: int
    data: Any
    ok: bool


class RestApiNode(BaseNode[RestApiInput, RestApiOutput]):
    metadata = NodeMetadata(
        node_id=_NODE_ID,
        name="REST API",
        category="integration",
        risk_level=RiskLevel.MEDIUM,
        is_mvp=True,
    )
    input_schema = RestApiInput
    output_schema = RestApiOutput

    async def process(self, input: RestApiInput, context: NodeContext) -> RestApiOutput:
        base_url = input.base_url.rstrip("/")
        path = input.path.lstrip("/")
        url = f"{base_url}/{path}" if path else base_url
        await validate_outbound_url(url)

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            **input.headers,
        }
        # credential 노드일 때 해결된 토큰을 Bearer로 주입 (ADR-0018). 작성자가 명시한
        # Authorization 헤더가 있으면 그대로 둔다.
        if context.connection_token and not any(k.lower() == "authorization" for k in headers):
            headers["Authorization"] = f"Bearer {context.connection_token}"
        content = json.dumps(input.body).encode() if input.body is not None else None
        timeout = min(input.timeout_seconds, _MAX_TIMEOUT_SECONDS)

        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.request(
                method=input.method.upper(),
                url=url,
                headers=headers,
                content=content,
                params=input.query_params or None,
            )

        try:
            data: Any = json.loads(response.content)
        except (json.JSONDecodeError, UnicodeDecodeError):
            data = response.content.decode("utf-8", errors="replace")

        return RestApiOutput(
            status_code=response.status_code,
            data=data,
            ok=response.is_success,
        )


def get_node_definition() -> NodeDefinition:
    return NodeDefinition(
        node_id=_NODE_ID,
        node_type=_NODE_TYPE,
        name="REST API",
        category="integration",
        version="1.0.0",
        input_schema={
            "type": "object",
            "properties": {
                "base_url": {"type": "string", "description": 'API 기본 URL. 예: "https://api.example.com"'},
                "path": {
                    "type": "string",
                    "default": "",
                    "description": 'base_url에 이어붙일 경로. 예: "/v1/users". 기본값 빈 문자열',
                },
                "method": {
                    "type": "string",
                    "enum": ["GET", "POST", "PUT", "PATCH", "DELETE"],
                    "default": "GET",
                    "description": "HTTP 메서드(GET/POST/PUT/PATCH/DELETE). 기본값 GET",
                },
                "query_params": {"type": "object", "description": 'URL 쿼리 파라미터 객체. 예: {"page": 1}'},
                "headers": {
                    "type": "object",
                    "additionalProperties": {"type": "string"},
                    "description": "요청 HTTP 헤더 객체. 인증 토큰은 연결(credential)로 주입 권장",
                },
                "body": {"type": "object", "description": "POST/PUT/PATCH 요청 본문(JSON)"},
                "timeout_seconds": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 300,
                    "default": 30,
                    "description": "응답 대기 제한 시간(초). 기본값 30",
                },
            },
            "required": ["base_url"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "status_code": {"type": "integer"},
                "data": {},
                "ok": {"type": "boolean"},
            },
            "required": ["status_code", "data", "ok"],
        },
        parameter_schema={},
        risk_level=RiskLevel.MEDIUM,
        required_connections=[],
        description="REST API 호출 및 JSON 응답 파싱. base_url + path 조합, credential 선택적 지원",
        is_mvp=True,
        service_type=None,
    )
