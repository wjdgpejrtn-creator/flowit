from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import uuid5

from common_schemas.enums import RiskLevel

from ....domain.entities.base_node import BaseNode
from ....domain.entities.node_definition import NodeDefinition
from ....domain.entities.node_metadata import NodeMetadata
from ....domain.catalog._catalog_ns import _CATALOG_NS

_NODE_TYPE = "json_transform"
_NODE_ID = uuid5(_CATALOG_NS, _NODE_TYPE)


@dataclass
class JsonTransformInput:
    data: dict[str, Any]
    expression: str


@dataclass
class JsonTransformOutput:
    result: Any
    matched: bool


class JsonTransformNode(BaseNode[JsonTransformInput, JsonTransformOutput]):
    metadata = NodeMetadata(
        node_id=_NODE_ID,
        name="JSON 변환 (JMESPath)",
        category="transform",
        risk_level=RiskLevel.LOW,
        is_mvp=True,
    )
    input_schema = JsonTransformInput
    output_schema = JsonTransformOutput

    async def process(self, input: JsonTransformInput) -> JsonTransformOutput:
        raise NotImplementedError(
            "JSON 변환은 REQ-005 toolset.JsonTransformTool을 통해 처리. "
            "execution_engine.ToolsetExecutor가 node_type 기반으로 toolset.execute_tool() 호출. "
            "BaseNode.process() 직접 호출 X."
        )


def get_node_definition() -> NodeDefinition:
    return NodeDefinition(
        node_id=_NODE_ID,
        node_type=_NODE_TYPE,
        name="JSON 변환 (JMESPath)",
        category="transform",
        version="1.0.0",
        input_schema={
            "type": "object",
            "properties": {
                "data": {"type": "object"},
                "expression": {"type": "string"},
            },
            "required": ["data", "expression"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "result": {},
                "matched": {"type": "boolean"},
            },
            "required": ["result", "matched"],
        },
        parameter_schema={},
        risk_level=RiskLevel.LOW,
        required_connections=[],
        description="JMESPath 표현식으로 JSON 데이터 추출/변환. wildcard([*]), filter([?field]) 지원",
        is_mvp=True,
        service_type=None,
    )
