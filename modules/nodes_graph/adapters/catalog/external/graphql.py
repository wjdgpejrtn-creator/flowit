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

_NODE_TYPE = "graphql"
_NODE_ID = uuid5(_CATALOG_NS, _NODE_TYPE)


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
        raise NotImplementedError(
            "GraphQL 호출은 REQ-005 toolset.GraphqlTool을 통해 처리. "
            "execution_engine.ToolsetExecutor가 node_type 기반으로 toolset.execute_tool() 호출. "
            "BaseNode.process() 직접 호출 X."
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
