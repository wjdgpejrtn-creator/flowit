from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import uuid5

from common_schemas.enums import RiskLevel

from ....domain.entities.base_node import BaseNode
from ....domain.entities.node_definition import NodeDefinition
from ....domain.entities.node_metadata import NodeMetadata
from .._catalog_ns import _CATALOG_NS

_NODE_TYPE = "json_extract"
_NODE_ID = uuid5(_CATALOG_NS, _NODE_TYPE)


@dataclass
class JsonExtractInput:
    data: dict[str, Any]
    path: str  # dot-separated: "user.profile.name" or "items.0.id"


@dataclass
class JsonExtractOutput:
    value: Any
    found: bool


class JsonExtractNode(BaseNode[JsonExtractInput, JsonExtractOutput]):
    metadata = NodeMetadata(
        node_id=_NODE_ID,
        name="JSON 값 추출",
        category="데이터 처리",
        risk_level=RiskLevel.LOW,
        is_mvp=True,
    )
    input_schema = JsonExtractInput
    output_schema = JsonExtractOutput

    async def process(self, input: JsonExtractInput) -> JsonExtractOutput:
        current: Any = input.data
        for key in input.path.split("."):
            if current is None:
                return JsonExtractOutput(value=None, found=False)
            if isinstance(current, dict):
                current = current.get(key)
            elif isinstance(current, list):
                try:
                    current = current[int(key)]
                except (IndexError, ValueError):
                    return JsonExtractOutput(value=None, found=False)
            else:
                return JsonExtractOutput(value=None, found=False)
        return JsonExtractOutput(value=current, found=current is not None)


def get_node_definition() -> NodeDefinition:
    return NodeDefinition(
        node_id=_NODE_ID,
        node_type=_NODE_TYPE,
        name="JSON 값 추출",
        category="데이터 처리",
        version="1.0.0",
        input_schema={
            "type": "object",
            "properties": {
                "data": {"type": "object"},
                "path": {"type": "string", "description": "점(.) 구분 경로 (예: user.profile.name)"},
            },
            "required": ["data", "path"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "value": {},
                "found": {"type": "boolean"},
            },
        },
        parameter_schema={},
        risk_level=RiskLevel.LOW,
        required_connections=[],
        description="JSON 객체에서 점(.) 구분 경로로 값을 추출",
        is_mvp=True,
        service_type=None,
    )
