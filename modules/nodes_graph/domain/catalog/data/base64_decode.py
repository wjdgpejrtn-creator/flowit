from __future__ import annotations

import base64
from dataclasses import dataclass
from uuid import uuid5

from common_schemas.enums import RiskLevel

from ....domain.entities.base_node import BaseNode
from ....domain.entities.node_definition import NodeDefinition
from ....domain.entities.node_metadata import NodeMetadata
from .._catalog_ns import _CATALOG_NS

_NODE_TYPE = "base64_decode"
_NODE_ID = uuid5(_CATALOG_NS, _NODE_TYPE)


@dataclass
class Base64DecodeInput:
    data: str
    encoding: str = "utf-8"


@dataclass
class Base64DecodeOutput:
    result: str


class Base64DecodeNode(BaseNode[Base64DecodeInput, Base64DecodeOutput]):
    metadata = NodeMetadata(
        node_id=_NODE_ID,
        name="Base64 디코딩",
        category="데이터 처리",
        risk_level=RiskLevel.LOW,
        is_mvp=True,
    )
    input_schema = Base64DecodeInput
    output_schema = Base64DecodeOutput

    async def process(self, input: Base64DecodeInput) -> Base64DecodeOutput:
        decoded = base64.b64decode(input.data.encode("ascii")).decode(input.encoding)
        return Base64DecodeOutput(result=decoded)


def get_node_definition() -> NodeDefinition:
    return NodeDefinition(
        node_id=_NODE_ID,
        node_type=_NODE_TYPE,
        name="Base64 디코딩",
        category="데이터 처리",
        version="1.0.0",
        input_schema={
            "type": "object",
            "properties": {
                "data": {"type": "string"},
                "encoding": {"type": "string", "default": "utf-8"},
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
        description="Base64 문자열을 디코딩하여 원본 문자열 반환",
        is_mvp=True,
        service_type=None,
    )
