from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid5

from common_schemas.enums import RiskLevel

from ...domain.entities.base_node import BaseNode
from ...domain.entities.node_definition import NodeDefinition
from ...domain.entities.node_metadata import NodeMetadata
from .._catalog_ns import _CATALOG_NS

_NODE_TYPE = "manual_trigger"
_NODE_ID = uuid5(_CATALOG_NS, _NODE_TYPE)


@dataclass
class ManualTriggerInput:
    payload: dict[str, Any] = field(default_factory=dict)
    triggered_by: str = ""
    triggered_at: str = ""


@dataclass
class ManualTriggerOutput:
    payload: dict[str, Any]
    triggered_by: str
    triggered_at: str


class ManualTriggerNode(BaseNode[ManualTriggerInput, ManualTriggerOutput]):
    metadata = NodeMetadata(
        node_id=_NODE_ID,
        name="수동 트리거",
        category="트리거",
        risk_level=RiskLevel.LOW,
        is_mvp=True,
    )
    input_schema = ManualTriggerInput
    output_schema = ManualTriggerOutput

    async def process(self, input: ManualTriggerInput) -> ManualTriggerOutput:
        return ManualTriggerOutput(
            payload=input.payload,
            triggered_by=input.triggered_by,
            triggered_at=input.triggered_at,
        )


def get_node_definition() -> NodeDefinition:
    return NodeDefinition(
        node_id=_NODE_ID,
        node_type=_NODE_TYPE,
        name="수동 트리거",
        category="트리거",
        version="1.0.0",
        input_schema={
            "type": "object",
            "properties": {
                "payload": {"type": "object"},
                "triggered_by": {"type": "string"},
                "triggered_at": {"type": "string"},
            },
        },
        output_schema={
            "type": "object",
            "properties": {
                "payload": {"type": "object"},
                "triggered_by": {"type": "string"},
                "triggered_at": {"type": "string"},
            },
        },
        parameter_schema={},
        risk_level=RiskLevel.LOW,
        required_connections=[],
        description="사용자가 수동으로 워크플로우를 시작. 선택적 초기 페이로드 전달 가능",
        is_mvp=True,
        service_type=None,
    )
