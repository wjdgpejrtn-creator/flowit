from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid5

import httpx
from common_schemas import NodeContext
from common_schemas.enums import RiskLevel
from common_schemas.exceptions import ExecutionError

from ....domain.catalog._catalog_ns import _CATALOG_NS
from ....domain.entities.base_node import BaseNode
from ....domain.entities.node_definition import NodeDefinition
from ....domain.entities.node_metadata import NodeMetadata
from ._url_guard import validate_outbound_url

_NODE_TYPE = "graphql"
_NODE_ID = uuid5(_CATALOG_NS, _NODE_TYPE)
_MAX_TIMEOUT_SECONDS = 300  # input_schema의 timeout_seconds maximum과 정합


@dataclass
class GraphqlInput:
    endpoint: str
    query: str
    variables: dict[str, Any] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)
    timeout_seconds: int = 30


@dataclass
class GraphqlOutput:
    data: Any
    errors: list[dict[str, Any]] = field(default_factory=list)
    ok: bool = True


class GraphqlNode(BaseNode[GraphqlInput, GraphqlOutput]):
    metadata = NodeMetadata(
        node_id=_NODE_ID,
        name="GraphQL",
        category="integration",
        risk_level=RiskLevel.MEDIUM,
        is_mvp=True,
    )
    input_schema = GraphqlInput
    output_schema = GraphqlOutput

    async def process(self, input: GraphqlInput, context: NodeContext) -> GraphqlOutput:
        await validate_outbound_url(input.endpoint)

        payload: dict[str, Any] = {"query": input.query}
        if input.variables:
            payload["variables"] = input.variables
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            **input.headers,
        }
        # credential 노드일 때 해결된 토큰을 Bearer로 주입 (ADR-0018).
        if context.connection_token and not any(k.lower() == "authorization" for k in headers):
            headers["Authorization"] = f"Bearer {context.connection_token}"
        timeout = min(input.timeout_seconds, _MAX_TIMEOUT_SECONDS)

        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(input.endpoint, json=payload, headers=headers)

        try:
            result = json.loads(response.content)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            raise ExecutionError(f"GraphQL response is not valid JSON: {e}") from e

        errors = result.get("errors") or []
        return GraphqlOutput(
            data=result.get("data"),
            errors=errors,
            ok=response.status_code < 300 and not errors,
        )


def get_node_definition() -> NodeDefinition:
    return NodeDefinition(
        node_id=_NODE_ID,
        node_type=_NODE_TYPE,
        name="GraphQL",
        category="integration",
        version="1.0.0",
        input_schema={
            "type": "object",
            "properties": {
                "endpoint": {"type": "string"},
                "query": {"type": "string"},
                "variables": {"type": "object"},
                "headers": {"type": "object"},
                "timeout_seconds": {"type": "integer", "minimum": 1, "maximum": 300, "default": 30},
            },
            "required": ["endpoint", "query"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "data": {},
                "errors": {"type": "array"},
                "ok": {"type": "boolean"},
            },
            "required": ["data", "ok"],
        },
        parameter_schema={},
        risk_level=RiskLevel.MEDIUM,
        required_connections=[],
        description="GraphQL 쿼리/뮤테이션 실행",
        is_mvp=True,
        service_type=None,
    )
