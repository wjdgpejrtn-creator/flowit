from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid5

from common_schemas.enums import RiskLevel

from ....domain.entities.base_node import BaseNode
from ....domain.entities.node_definition import NodeDefinition
from ....domain.entities.node_metadata import NodeMetadata
from .._catalog_ns import _CATALOG_NS

_NODE_TYPE = "text_transform"
_NODE_ID = uuid5(_CATALOG_NS, _NODE_TYPE)


@dataclass
class TextTransformInput:
    text: str
    operation: str  # upper | lower | strip | title | reverse


@dataclass
class TextTransformOutput:
    result: str


class TextTransformNode(BaseNode[TextTransformInput, TextTransformOutput]):
    metadata = NodeMetadata(
        node_id=_NODE_ID,
        name="텍스트 변환",
        category="transform",
        risk_level=RiskLevel.LOW,
        is_mvp=True,
    )
    input_schema = TextTransformInput
    output_schema = TextTransformOutput

    async def process(self, input: TextTransformInput) -> TextTransformOutput:
        match input.operation:
            case "upper":
                result = input.text.upper()
            case "lower":
                result = input.text.lower()
            case "strip":
                result = input.text.strip()
            case "title":
                result = input.text.title()
            case "reverse":
                result = input.text[::-1]
            case _:
                result = input.text
        return TextTransformOutput(result=result)


def get_node_definition() -> NodeDefinition:
    return NodeDefinition(
        node_id=_NODE_ID,
        node_type=_NODE_TYPE,
        name="텍스트 변환",
        category="transform",
        version="1.0.0",
        input_schema={
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "operation": {"type": "string", "enum": ["upper", "lower", "strip", "title", "reverse"]},
            },
            "required": ["text", "operation"],
        },
        output_schema={
            "type": "object",
            "properties": {"result": {"type": "string"}},
        },
        parameter_schema={},
        risk_level=RiskLevel.LOW,
        required_connections=[],
        description="텍스트 대소문자 변환, 공백 제거, 역순 등 문자열 변환",
        is_mvp=True,
        service_type=None,
    )
