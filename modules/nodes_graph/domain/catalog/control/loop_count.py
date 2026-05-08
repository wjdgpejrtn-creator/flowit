from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid5

from common_schemas.enums import RiskLevel

from ....domain.entities.base_node import BaseNode
from ....domain.entities.node_definition import NodeDefinition
from ....domain.entities.node_metadata import NodeMetadata
from .._catalog_ns import _CATALOG_NS

_NODE_TYPE = "loop_count"
_NODE_ID = uuid5(_CATALOG_NS, _NODE_TYPE)


@dataclass
class LoopCountInput:
    count: int
    start: int = 0


@dataclass
class LoopCountOutput:
    count: int
    indices: list[int]


class LoopCountNode(BaseNode[LoopCountInput, LoopCountOutput]):
    metadata = NodeMetadata(
        node_id=_NODE_ID,
        name="횟수 반복",
        category="조건/제어",
        risk_level=RiskLevel.LOW,
        is_mvp=True,
    )
    input_schema = LoopCountInput
    output_schema = LoopCountOutput

    async def process(self, input: LoopCountInput) -> LoopCountOutput:
        indices = list(range(input.start, input.start + input.count))
        return LoopCountOutput(count=input.count, indices=indices)


def get_node_definition() -> NodeDefinition:
    return NodeDefinition(
        node_id=_NODE_ID,
        node_type=_NODE_TYPE,
        name="횟수 반복",
        category="조건/제어",
        version="1.0.0",
        input_schema={
            "type": "object",
            "properties": {
                "count": {"type": "integer"},
                "start": {"type": "integer", "default": 0},
            },
            "required": ["count"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "count": {"type": "integer"},
                "indices": {"type": "array", "items": {"type": "integer"}},
            },
        },
        parameter_schema={},
        risk_level=RiskLevel.LOW,
        required_connections=[],
        description="지정한 횟수만큼 하위 노드를 반복 실행 (실행 엔진 처리)",
        is_mvp=True,
        service_type=None,
    )
