from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import uuid5

from common_schemas import NodeContext
from common_schemas.enums import RiskLevel
from common_schemas.exceptions import ValidationError

from ....domain.catalog._catalog_ns import _CATALOG_NS
from ....domain.entities.base_node import BaseNode
from ....domain.entities.node_definition import NodeDefinition
from ....domain.entities.node_metadata import NodeMetadata

_NODE_TYPE = "data_mapping"
_NODE_ID = uuid5(_CATALOG_NS, _NODE_TYPE)


@dataclass
class DataMappingInput:
    data: dict[str, Any]
    mapping: dict[str, str]                                     # {old_field: new_field}
    drop_unmapped: bool = False


@dataclass
class DataMappingOutput:
    result: dict[str, Any]
    mapped_count: int


class DataMappingNode(BaseNode[DataMappingInput, DataMappingOutput]):
    metadata = NodeMetadata(
        node_id=_NODE_ID,
        name="데이터 매핑",
        category="transform",
        risk_level=RiskLevel.LOW,
        is_mvp=True,
    )
    input_schema = DataMappingInput
    output_schema = DataMappingOutput

    async def process(self, input: DataMappingInput, context: NodeContext) -> DataMappingOutput:
        if not isinstance(input.data, dict):
            raise ValidationError("'data' must be a JSON object")
        result: dict[str, Any] = {}
        mapped_count = 0
        for key, value in input.data.items():
            if key in input.mapping:
                result[input.mapping[key]] = value
                mapped_count += 1
            elif not input.drop_unmapped:
                result[key] = value
        return DataMappingOutput(result=result, mapped_count=mapped_count)


def get_node_definition() -> NodeDefinition:
    return NodeDefinition(
        node_id=_NODE_ID,
        node_type=_NODE_TYPE,
        name="데이터 매핑",
        category="transform",
        version="1.0.0",
        input_schema={
            "type": "object",
            "properties": {
                "data": {"type": "object"},
                "mapping": {"type": "object"},
                "drop_unmapped": {"type": "boolean", "default": False},
            },
            "required": ["data", "mapping"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "result": {"type": "object"},
                "mapped_count": {"type": "integer"},
            },
            "required": ["result", "mapped_count"],
        },
        parameter_schema={},
        risk_level=RiskLevel.LOW,
        required_connections=[],
        description="필드명 리매핑. drop_unmapped=true 시 매핑 미정의 필드 제거",
        is_mvp=True,
        service_type=None,
    )
