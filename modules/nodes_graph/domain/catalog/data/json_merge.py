from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import uuid5

from common_schemas import NodeContext
from common_schemas.enums import RiskLevel

from ....domain.entities.base_node import BaseNode
from ....domain.entities.node_definition import NodeDefinition
from ....domain.entities.node_metadata import NodeMetadata
from .._catalog_ns import _CATALOG_NS

_NODE_TYPE = "json_merge"
_NODE_ID = uuid5(_CATALOG_NS, _NODE_TYPE)


@dataclass
class JsonMergeInput:
    base: dict[str, Any]
    overlay: dict[str, Any]
    deep: bool = False  # True: 재귀 병합, False: 얕은 병합


@dataclass
class JsonMergeOutput:
    result: dict[str, Any]


def _deep_merge(base: dict, overlay: dict) -> dict:
    result = dict(base)
    for key, value in overlay.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


class JsonMergeNode(BaseNode[JsonMergeInput, JsonMergeOutput]):
    metadata = NodeMetadata(
        node_id=_NODE_ID,
        name="JSON 병합",
        category="transform",
        risk_level=RiskLevel.LOW,
        is_mvp=True,
    )
    input_schema = JsonMergeInput
    output_schema = JsonMergeOutput

    async def process(self, input: JsonMergeInput, context: NodeContext) -> JsonMergeOutput:
        if input.deep:
            result = _deep_merge(input.base, input.overlay)
        else:
            result = {**input.base, **input.overlay}
        return JsonMergeOutput(result=result)


def get_node_definition() -> NodeDefinition:
    return NodeDefinition(
        node_id=_NODE_ID,
        node_type=_NODE_TYPE,
        name="JSON 병합",
        category="transform",
        version="1.0.0",
        input_schema={
            "type": "object",
            "properties": {
                "base": {"type": "object", "description": "기준이 되는 JSON 객체. overlay가 같은 키를 덮어씁니다"},
                "overlay": {"type": "object", "description": "base 위에 덮어쓸 JSON 객체"},
                "deep": {
                    "type": "boolean",
                    "default": False,
                    "description": "true면 중첩 객체까지 재귀 병합, false면 최상위 키만 병합. 기본값 false",
                },
            },
            "required": ["base", "overlay"],
        },
        output_schema={
            "type": "object",
            "properties": {"result": {"type": "object"}},
        },
        parameter_schema={},
        risk_level=RiskLevel.LOW,
        required_connections=[],
        description="두 JSON 객체를 병합. deep=True 시 중첩 객체도 재귀 병합",
        is_mvp=True,
        service_type=None,
    )
