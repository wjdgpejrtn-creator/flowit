from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import uuid5

from common_schemas.enums import RiskLevel

from ....domain.entities.base_node import BaseNode
from ....domain.entities.node_definition import NodeDefinition
from ....domain.entities.node_metadata import NodeMetadata
from .._catalog_ns import _CATALOG_NS

_NODE_TYPE = "switch_case"
_NODE_ID = uuid5(_CATALOG_NS, _NODE_TYPE)


@dataclass
class SwitchCaseInput:
    value: Any
    cases: list[str]    # 정의된 케이스 목록
    default_case: str = "default"


@dataclass
class SwitchCaseOutput:
    matched_case: str
    value: Any


class SwitchCaseNode(BaseNode[SwitchCaseInput, SwitchCaseOutput]):
    metadata = NodeMetadata(
        node_id=_NODE_ID,
        name="다중 분기",
        category="condition",
        risk_level=RiskLevel.LOW,
        is_mvp=True,
    )
    input_schema = SwitchCaseInput
    output_schema = SwitchCaseOutput

    async def process(self, input: SwitchCaseInput) -> SwitchCaseOutput:
        str_value = str(input.value)
        matched = str_value if str_value in input.cases else input.default_case
        return SwitchCaseOutput(matched_case=matched, value=input.value)


def get_node_definition() -> NodeDefinition:
    return NodeDefinition(
        node_id=_NODE_ID,
        node_type=_NODE_TYPE,
        name="다중 분기",
        category="condition",
        version="1.0.0",
        input_schema={
            "type": "object",
            "properties": {
                "value": {},
                "cases": {"type": "array", "items": {"type": "string"}},
                "default_case": {"type": "string", "default": "default"},
            },
            "required": ["value", "cases"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "matched_case": {"type": "string"},
                "value": {},
            },
        },
        parameter_schema={},
        risk_level=RiskLevel.LOW,
        required_connections=[],
        description="값에 따라 N개 케이스 중 하나로 분기",
        is_mvp=True,
        service_type=None,
    )
