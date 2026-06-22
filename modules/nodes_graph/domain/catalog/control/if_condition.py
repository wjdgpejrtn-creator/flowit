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

_NODE_TYPE = "if_condition"
_NODE_ID = uuid5(_CATALOG_NS, _NODE_TYPE)


@dataclass
class IfConditionInput:
    left: Any
    operator: str  # eq | ne | gt | lt | gte | lte | in | not_in | is_none | is_not_none | contains
    right: Any = None
    value: Any = None  # 다음 노드로 전달할 pass-through 값


@dataclass
class IfConditionOutput:
    branch: str  # "true" | "false"
    value: Any
    condition_result: bool


class IfConditionNode(BaseNode[IfConditionInput, IfConditionOutput]):
    metadata = NodeMetadata(
        node_id=_NODE_ID,
        name="조건 분기",
        category="condition",
        risk_level=RiskLevel.LOW,
        is_mvp=True,
    )
    input_schema = IfConditionInput
    output_schema = IfConditionOutput

    async def process(self, input: IfConditionInput, context: NodeContext) -> IfConditionOutput:
        match input.operator:
            case "eq":
                result = input.left == input.right
            case "ne":
                result = input.left != input.right
            case "gt":
                result = input.left > input.right
            case "lt":
                result = input.left < input.right
            case "gte":
                result = input.left >= input.right
            case "lte":
                result = input.left <= input.right
            case "in":
                result = input.left in input.right
            case "not_in":
                result = input.left not in input.right
            case "is_none":
                result = input.left is None
            case "is_not_none":
                result = input.left is not None
            case "contains":
                result = str(input.right) in str(input.left)
            case _:
                result = bool(input.left)
        return IfConditionOutput(
            branch="true" if result else "false",
            value=input.value,
            condition_result=result,
        )


def get_node_definition() -> NodeDefinition:
    return NodeDefinition(
        node_id=_NODE_ID,
        node_type=_NODE_TYPE,
        name="조건 분기",
        category="condition",
        version="1.0.0",
        input_schema={
            "type": "object",
            "properties": {
                "left": {"description": "비교할 왼쪽 값(피연산자)"},
                "operator": {
                    "type": "string",
                    "enum": [
                        "eq",
                        "ne",
                        "gt",
                        "lt",
                        "gte",
                        "lte",
                        "in",
                        "not_in",
                        "is_none",
                        "is_not_none",
                        "contains",
                    ],
                    "description": (
                        "비교 연산자. eq=같음, ne=다름, gt=초과, lt=미만, gte=이상, lte=이하, "
                        "in=포함됨, not_in=포함안됨, is_none=값없음, is_not_none=값있음, contains=포함"
                    ),
                },
                "right": {"description": "비교할 오른쪽 값. is_none/is_not_none에서는 불필요"},
                "value": {"description": "조건이 참일 때 다음 노드로 전달할 값. 비우면 left를 전달"},
            },
            "required": ["left", "operator"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "branch": {"type": "string", "enum": ["true", "false"]},
                "value": {},
                "condition_result": {"type": "boolean"},
            },
        },
        parameter_schema={},
        risk_level=RiskLevel.LOW,
        required_connections=[],
        description="조건 평가 결과에 따라 true/false 브랜치로 분기",
        is_mvp=True,
        service_type=None,
    )
