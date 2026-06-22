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

_NODE_TYPE = "merge_branch"
_NODE_ID = uuid5(_CATALOG_NS, _NODE_TYPE)


@dataclass
class MergeBranchInput:
    branches: list[Any]
    strategy: str = "list"  # list | first | last | dict_merge


@dataclass
class MergeBranchOutput:
    result: Any
    branch_count: int


class MergeBranchNode(BaseNode[MergeBranchInput, MergeBranchOutput]):
    metadata = NodeMetadata(
        node_id=_NODE_ID,
        name="브랜치 병합",
        category="condition",
        risk_level=RiskLevel.LOW,
        is_mvp=True,
    )
    input_schema = MergeBranchInput
    output_schema = MergeBranchOutput

    async def process(self, input: MergeBranchInput, context: NodeContext) -> MergeBranchOutput:
        match input.strategy:
            case "list":
                result: Any = list(input.branches)
            case "first":
                result = input.branches[0] if input.branches else None
            case "last":
                result = input.branches[-1] if input.branches else None
            case "dict_merge":
                merged: dict[str, Any] = {}
                for b in input.branches:
                    if isinstance(b, dict):
                        merged.update(b)
                result = merged
            case _:
                result = list(input.branches)
        return MergeBranchOutput(result=result, branch_count=len(input.branches))


def get_node_definition() -> NodeDefinition:
    return NodeDefinition(
        node_id=_NODE_ID,
        node_type=_NODE_TYPE,
        name="브랜치 병합",
        category="condition",
        version="1.0.0",
        input_schema={
            "type": "object",
            "properties": {
                "branches": {"type": "array", "description": "병합할 병렬 브랜치 결과 목록"},
                "strategy": {
                    "type": "string",
                    "enum": ["list", "first", "last", "dict_merge"],
                    "default": "list",
                    "description": (
                        "병합 방식. list=배열로 모음, first=첫 결과, last=마지막 결과, "
                        "dict_merge=객체 병합. 기본값 list"
                    ),
                },
            },
            "required": ["branches"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "result": {},
                "branch_count": {"type": "integer"},
            },
        },
        parameter_schema={},
        risk_level=RiskLevel.LOW,
        required_connections=[],
        description="병렬 브랜치 결과를 하나로 집계 (list/first/last/dict_merge 전략)",
        is_mvp=True,
        service_type=None,
    )
