from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import uuid5

from common_schemas.enums import RiskLevel

from ....domain.entities.base_node import BaseNode
from ....domain.entities.node_definition import NodeDefinition
from ....domain.entities.node_metadata import NodeMetadata
from .._catalog_ns import _CATALOG_NS

_NODE_TYPE = "list_filter"
_NODE_ID = uuid5(_CATALOG_NS, _NODE_TYPE)


@dataclass
class ListFilterInput:
    items: list[Any]
    operation: str  # filter_none | sort | sort_desc | deduplicate | reverse | take | skip
    n: int = 0          # take/skip 개수
    key: str = ""       # dict 리스트 정렬 시 기준 필드명


@dataclass
class ListFilterOutput:
    result: list[Any]
    count: int


class ListFilterNode(BaseNode[ListFilterInput, ListFilterOutput]):
    metadata = NodeMetadata(
        node_id=_NODE_ID,
        name="리스트 필터",
        category="transform",
        risk_level=RiskLevel.LOW,
        is_mvp=True,
    )
    input_schema = ListFilterInput
    output_schema = ListFilterOutput

    async def process(self, input: ListFilterInput) -> ListFilterOutput:
        items = list(input.items)
        match input.operation:
            case "filter_none":
                items = [x for x in items if x is not None]
            case "sort":
                if input.key and items and isinstance(items[0], dict):
                    items = sorted(items, key=lambda x: x.get(input.key, ""))
                else:
                    items = sorted(items)
            case "sort_desc":
                if input.key and items and isinstance(items[0], dict):
                    items = sorted(items, key=lambda x: x.get(input.key, ""), reverse=True)
                else:
                    items = sorted(items, reverse=True)
            case "deduplicate":
                seen: list[Any] = []
                for x in items:
                    if x not in seen:
                        seen.append(x)
                items = seen
            case "reverse":
                items = list(reversed(items))
            case "take":
                items = items[: input.n]
            case "skip":
                items = items[input.n :]
        return ListFilterOutput(result=items, count=len(items))


def get_node_definition() -> NodeDefinition:
    return NodeDefinition(
        node_id=_NODE_ID,
        node_type=_NODE_TYPE,
        name="리스트 필터",
        category="transform",
        version="1.0.0",
        input_schema={
            "type": "object",
            "properties": {
                "items": {"type": "array"},
                "operation": {
                    "type": "string",
                    "enum": ["filter_none", "sort", "sort_desc", "deduplicate", "reverse", "take", "skip"],
                },
                "n": {"type": "integer", "default": 0},
                "key": {"type": "string", "default": ""},
            },
            "required": ["items", "operation"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "result": {"type": "array"},
                "count": {"type": "integer"},
            },
        },
        parameter_schema={},
        risk_level=RiskLevel.LOW,
        required_connections=[],
        description="리스트 필터링, 정렬, 중복 제거, 슬라이스 등",
        is_mvp=True,
        service_type=None,
    )
