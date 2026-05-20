from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid5

from common_schemas import NodeContext
from common_schemas.enums import RiskLevel

from ....domain.entities.base_node import BaseNode
from ....domain.entities.node_definition import NodeDefinition
from ....domain.entities.node_metadata import NodeMetadata
from ....domain.catalog._catalog_ns import _CATALOG_NS

_NODE_TYPE = "rest_api"
_NODE_ID = uuid5(_CATALOG_NS, _NODE_TYPE)


@dataclass
class RestApiInput:
    base_url: str
    path: str = ""
    method: str = "GET"                                         # GET | POST | PUT | PATCH | DELETE
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
        raise NotImplementedError(
            "REST API 호출은 REQ-005 toolset.RestApiTool을 통해 처리. "
            "execution_engine.ToolsetExecutor가 node_type 기반으로 toolset.execute_tool() 호출. "
            "BaseNode.process() 직접 호출 X."
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
                "base_url": {"type": "string"},
                "path": {"type": "string", "default": ""},
                "method": {
                    "type": "string",
                    "enum": ["GET", "POST", "PUT", "PATCH", "DELETE"],
                    "default": "GET",
                },
                "query_params": {"type": "object"},
                "headers": {"type": "object", "additionalProperties": {"type": "string"}},
                "body": {"type": "object"},
                "timeout_seconds": {"type": "integer", "minimum": 1, "maximum": 300, "default": 30},
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
