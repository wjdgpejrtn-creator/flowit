from __future__ import annotations

import base64
from dataclasses import dataclass
from uuid import uuid5

from common_schemas import NodeContext
from common_schemas.enums import RiskLevel

from ....domain.entities.base_node import BaseNode
from ....domain.entities.node_definition import NodeDefinition
from ....domain.entities.node_metadata import NodeMetadata
from .._catalog_ns import _CATALOG_NS

_NODE_TYPE = "base64_encode"
_NODE_ID = uuid5(_CATALOG_NS, _NODE_TYPE)


@dataclass
class Base64EncodeInput:
    data: str
    encoding: str = "utf-8"


@dataclass
class Base64EncodeOutput:
    result: str


class Base64EncodeNode(BaseNode[Base64EncodeInput, Base64EncodeOutput]):
    metadata = NodeMetadata(
        node_id=_NODE_ID,
        name="Base64 인코딩",
        category="transform",
        risk_level=RiskLevel.LOW,
        is_mvp=True,
    )
    input_schema = Base64EncodeInput
    output_schema = Base64EncodeOutput

    async def process(self, input: Base64EncodeInput, context: NodeContext) -> Base64EncodeOutput:
        encoded = base64.b64encode(input.data.encode(input.encoding)).decode("ascii")
        return Base64EncodeOutput(result=encoded)


def get_node_definition() -> NodeDefinition:
    return NodeDefinition(
        node_id=_NODE_ID,
        node_type=_NODE_TYPE,
        name="Base64 인코딩",
        category="transform",
        version="1.0.0",
        input_schema={
            "type": "object",
            "properties": {
                "data": {"type": "string", "description": "인코딩할 원본 문자열"},
                "encoding": {
                    "type": "string",
                    "default": "utf-8",
                    "description": "원본 문자열의 문자 인코딩. 기본값 utf-8",
                },
            },
            "required": ["data"],
        },
        output_schema={
            "type": "object",
            "properties": {"result": {"type": "string"}},
        },
        parameter_schema={},
        risk_level=RiskLevel.LOW,
        required_connections=[],
        description="문자열을 Base64로 인코딩",
        is_mvp=True,
        service_type=None,
    )
