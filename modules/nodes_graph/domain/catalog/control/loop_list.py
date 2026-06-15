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

_NODE_TYPE = "loop_list"
_NODE_ID = uuid5(_CATALOG_NS, _NODE_TYPE)


@dataclass
class LoopListInput:
    items: list[Any]


@dataclass
class LoopListOutput:
    items: list[Any]
    count: int
    # 실행 엔진이 items를 순회하며 하위 노드를 반복 실행


class LoopListNode(BaseNode[LoopListInput, LoopListOutput]):
    metadata = NodeMetadata(
        node_id=_NODE_ID,
        name="리스트 순회",
        category="condition",
        risk_level=RiskLevel.LOW,
        is_mvp=True,
    )
    input_schema = LoopListInput
    output_schema = LoopListOutput

    async def process(self, input: LoopListInput, context: NodeContext) -> LoopListOutput:
        return LoopListOutput(items=list(input.items), count=len(input.items))


def get_node_definition() -> NodeDefinition:
    return NodeDefinition(
        node_id=_NODE_ID,
        node_type=_NODE_TYPE,
        name="리스트 순회",
        category="condition",
        version="1.0.0",
        input_schema={
            "type": "object",
            "properties": {"items": {"type": "array", "description": "각 항목마다 하위 노드를 반복 실행할 리스트"}},
            "required": ["items"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "items": {"type": "array"},
                "count": {"type": "integer"},
            },
        },
        parameter_schema={},
        risk_level=RiskLevel.LOW,
        required_connections=[],
        description="리스트 각 항목에 대해 하위 노드를 반복 실행 (실행 엔진 처리)",
        is_mvp=True,
        service_type=None,
    )
