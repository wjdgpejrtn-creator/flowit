from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid5

from common_schemas.enums import RiskLevel

from ...domain.entities.base_node import BaseNode
from ...domain.entities.node_definition import NodeDefinition
from ...domain.entities.node_metadata import NodeMetadata
from .._catalog_ns import _CATALOG_NS

_NODE_TYPE = "event_trigger"
_NODE_ID = uuid5(_CATALOG_NS, _NODE_TYPE)


@dataclass
class EventTriggerInput:
    event_type: str
    payload: dict[str, Any] = field(default_factory=dict)
    source: str = ""


@dataclass
class EventTriggerOutput:
    event_type: str
    payload: dict[str, Any]
    source: str


class EventTriggerNode(BaseNode[EventTriggerInput, EventTriggerOutput]):
    metadata = NodeMetadata(
        node_id=_NODE_ID,
        name="이벤트 트리거",
        category="트리거",
        risk_level=RiskLevel.LOW,
        is_mvp=True,
    )
    input_schema = EventTriggerInput
    output_schema = EventTriggerOutput

    async def process(self, input: EventTriggerInput) -> EventTriggerOutput:
        return EventTriggerOutput(
            event_type=input.event_type,
            payload=input.payload,
            source=input.source,
        )


def get_node_definition() -> NodeDefinition:
    return NodeDefinition(
        node_id=_NODE_ID,
        node_type=_NODE_TYPE,
        name="이벤트 트리거",
        category="트리거",
        version="1.0.0",
        input_schema={
            "type": "object",
            "properties": {
                "event_type": {"type": "string"},
                "payload": {"type": "object"},
                "source": {"type": "string"},
            },
            "required": ["event_type"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "event_type": {"type": "string"},
                "payload": {"type": "object"},
                "source": {"type": "string"},
            },
        },
        parameter_schema={},
        risk_level=RiskLevel.LOW,
        required_connections=[],
        description="내부 이벤트 버스 구독. 특정 event_type 발행 시 워크플로우 시작",
        is_mvp=True,
        service_type=None,
    )
