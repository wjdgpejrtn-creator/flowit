from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import uuid5

from common_schemas.enums import RiskLevel

from ...domain.entities.base_node import BaseNode
from ...domain.entities.node_definition import NodeDefinition
from ...domain.entities.node_metadata import NodeMetadata
from .._catalog_ns import _CATALOG_NS

_NODE_TYPE = "list_map"
_NODE_ID = uuid5(_CATALOG_NS, _NODE_TYPE)


@dataclass
class ListMapInput:
    items: list[Any]
    operation: str   # extract_field | to_str | to_int | to_float | upper | lower | strip
    field: str = ""  # extract_field 시 추출할 키 이름


@dataclass
class ListMapOutput:
    result: list[Any]
    count: int


class ListMapNode(BaseNode[ListMapInput, ListMapOutput]):
    metadata = NodeMetadata(
        node_id=_NODE_ID,
        name="리스트 변환",
        category="데이터 처리",
        risk_level=RiskLevel.LOW,
        is_mvp=True,
    )
    input_schema = ListMapInput
    output_schema = ListMapOutput

    async def process(self, input: ListMapInput) -> ListMapOutput:
        match input.operation:
            case "extract_field":
                result = [x.get(input.field) if isinstance(x, dict) else None for x in input.items]
            case "to_str":
                result = [str(x) for x in input.items]
            case "to_int":
                result = [int(x) for x in input.items]
            case "to_float":
                result = [float(x) for x in input.items]
            case "upper":
                result = [str(x).upper() for x in input.items]
            case "lower":
                result = [str(x).lower() for x in input.items]
            case "strip":
                result = [str(x).strip() for x in input.items]
            case _:
                result = list(input.items)
        return ListMapOutput(result=result, count=len(result))


def get_node_definition() -> NodeDefinition:
    return NodeDefinition(
        node_id=_NODE_ID,
        node_type=_NODE_TYPE,
        name="리스트 변환",
        category="데이터 처리",
        version="1.0.0",
        input_schema={
            "type": "object",
            "properties": {
                "items": {"type": "array"},
                "operation": {
                    "type": "string",
                    "enum": ["extract_field", "to_str", "to_int", "to_float", "upper", "lower", "strip"],
                },
                "field": {"type": "string", "default": ""},
            },
            "required": ["items", "operation"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "result": {"type": "array"},
                "count": {"type": "integer"},
            },
        },
        parameter_schema={},
        risk_level=RiskLevel.LOW,
        required_connections=[],
        description="리스트 각 요소에 변환 적용 (필드 추출, 타입 변환, 문자열 변환 등)",
        is_mvp=True,
        service_type=None,
    )
