from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid5

from common_schemas.enums import RiskLevel

from ....domain.entities.base_node import BaseNode
from ....domain.entities.node_definition import NodeDefinition
from ....domain.entities.node_metadata import NodeMetadata
from .._catalog_ns import _CATALOG_NS

_NODE_TYPE = "stop_workflow"
_NODE_ID = uuid5(_CATALOG_NS, _NODE_TYPE)


class StopWorkflowError(Exception):
    """워크플로우 강제 종료 시그널. 실행 엔진이 이 예외를 포착하여 정상 종료 처리한다."""


@dataclass
class StopWorkflowInput:
    reason: str = ""


@dataclass
class StopWorkflowOutput:
    stopped: bool
    reason: str


class StopWorkflowNode(BaseNode[StopWorkflowInput, StopWorkflowOutput]):
    metadata = NodeMetadata(
        node_id=_NODE_ID,
        name="워크플로우 종료",
        category="condition",
        risk_level=RiskLevel.LOW,
        is_mvp=True,
    )
    input_schema = StopWorkflowInput
    output_schema = StopWorkflowOutput

    async def process(self, input: StopWorkflowInput) -> StopWorkflowOutput:
        raise StopWorkflowError(input.reason)


def get_node_definition() -> NodeDefinition:
    return NodeDefinition(
        node_id=_NODE_ID,
        node_type=_NODE_TYPE,
        name="워크플로우 종료",
        category="condition",
        version="1.0.0",
        input_schema={
            "type": "object",
            "properties": {"reason": {"type": "string", "default": ""}},
        },
        output_schema={
            "type": "object",
            "properties": {
                "stopped": {"type": "boolean"},
                "reason": {"type": "string"},
            },
        },
        parameter_schema={},
        risk_level=RiskLevel.LOW,
        required_connections=[],
        description="워크플로우를 즉시 종료. StopWorkflowError를 발생시켜 실행 엔진이 정상 종료 처리",
        is_mvp=True,
        service_type=None,
    )
