from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import uuid5

import jmespath
import jmespath.exceptions
from common_schemas import NodeContext
from common_schemas.enums import RiskLevel
from common_schemas.exceptions import ValidationError

from ....domain.catalog._catalog_ns import _CATALOG_NS
from ....domain.entities.base_node import BaseNode
from ....domain.entities.node_definition import NodeDefinition
from ....domain.entities.node_metadata import NodeMetadata

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

    async def process(self, input: JsonTransformInput, context: NodeContext) -> JsonTransformOutput:
        if not input.expression.strip():
            raise ValidationError("expression must not be empty")
        try:
            result = jmespath.search(input.expression, input.data)
        except jmespath.exceptions.JMESPathError as e:
            raise ValidationError(f"Invalid JMESPath expression '{input.expression}': {e}") from e
        return JsonTransformOutput(result=result, matched=result is not None)


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
                "data": {"type": "object", "description": "변환할 대상 JSON 데이터"},
                "expression": {"type": "string", "description": 'JMESPath 표현식. 예: "items[?price > `100`].name"'},
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
