from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid5

from common_schemas import NodeContext
from common_schemas.enums import RiskLevel

from ....domain.entities.base_node import BaseNode
from ....domain.entities.node_definition import NodeDefinition
from ....domain.entities.node_metadata import NodeMetadata
from .._catalog_ns import _CATALOG_NS

_NODE_TYPE = "schedule_trigger"
_NODE_ID = uuid5(_CATALOG_NS, _NODE_TYPE)


@dataclass
class ScheduleTriggerInput:
    cron: str               # "0 9 * * 1-5" (평일 오전 9시)
    timezone: str = "UTC"
    triggered_at: str = "" # 실행 엔진이 주입하는 실제 트리거 시각 (ISO 형식)


@dataclass
class ScheduleTriggerOutput:
    triggered_at: str
    cron: str
    timezone: str


class ScheduleTriggerNode(BaseNode[ScheduleTriggerInput, ScheduleTriggerOutput]):
    metadata = NodeMetadata(
        node_id=_NODE_ID,
        name="스케줄 트리거",
        category="trigger",
        risk_level=RiskLevel.LOW,
        is_mvp=True,
    )
    input_schema = ScheduleTriggerInput
    output_schema = ScheduleTriggerOutput

    async def process(self, input: ScheduleTriggerInput, context: NodeContext) -> ScheduleTriggerOutput:
        return ScheduleTriggerOutput(
            triggered_at=input.triggered_at,
            cron=input.cron,
            timezone=input.timezone,
        )


def get_node_definition() -> NodeDefinition:
    return NodeDefinition(
        node_id=_NODE_ID,
        node_type=_NODE_TYPE,
        name="스케줄 트리거",
        category="trigger",
        version="1.0.0",
        input_schema={
            "type": "object",
            "properties": {
                "cron": {"type": "string", "description": "Cron 표현식 (예: '0 9 * * 1-5')"},
                "timezone": {"type": "string", "default": "UTC"},
                "triggered_at": {"type": "string"},
            },
            "required": ["cron"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "triggered_at": {"type": "string"},
                "cron": {"type": "string"},
                "timezone": {"type": "string"},
            },
        },
        parameter_schema={},
        risk_level=RiskLevel.LOW,
        required_connections=[],
        description="Cron 표현식 기반 스케줄 트리거. 실행 엔진이 스케줄을 관리하고 트리거 시각을 주입",
        is_mvp=True,
        service_type=None,
    )
