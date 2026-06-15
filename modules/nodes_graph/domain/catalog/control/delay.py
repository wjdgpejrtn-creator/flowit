from __future__ import annotations

import asyncio
from dataclasses import dataclass
from uuid import uuid5

from common_schemas import NodeContext
from common_schemas.enums import RiskLevel

from ....domain.entities.base_node import BaseNode
from ....domain.entities.node_definition import NodeDefinition
from ....domain.entities.node_metadata import NodeMetadata
from .._catalog_ns import _CATALOG_NS

_NODE_TYPE = "delay"
_NODE_ID = uuid5(_CATALOG_NS, _NODE_TYPE)


@dataclass
class DelayInput:
    seconds: float


@dataclass
class DelayOutput:
    elapsed_seconds: float


class DelayNode(BaseNode[DelayInput, DelayOutput]):
    metadata = NodeMetadata(
        node_id=_NODE_ID,
        name="지연 실행",
        category="condition",
        risk_level=RiskLevel.LOW,
        is_mvp=True,
    )
    input_schema = DelayInput
    output_schema = DelayOutput

    async def process(self, input: DelayInput, context: NodeContext) -> DelayOutput:
        await asyncio.sleep(input.seconds)
        return DelayOutput(elapsed_seconds=input.seconds)


def get_node_definition() -> NodeDefinition:
    return NodeDefinition(
        node_id=_NODE_ID,
        node_type=_NODE_TYPE,
        name="지연 실행",
        category="condition",
        version="1.0.0",
        input_schema={
            "type": "object",
            "properties": {
                "seconds": {"type": "number", "minimum": 0, "description": "실행을 지연시킬 시간(초). 예: 5"}
            },
            "required": ["seconds"],
        },
        output_schema={
            "type": "object",
            "properties": {"elapsed_seconds": {"type": "number"}},
        },
        parameter_schema={},
        risk_level=RiskLevel.LOW,
        required_connections=[],
        description="지정한 초(seconds)만큼 실행을 지연",
        is_mvp=True,
        service_type=None,
    )
