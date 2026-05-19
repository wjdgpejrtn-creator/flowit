from __future__ import annotations

import re
from dataclasses import dataclass
from uuid import uuid5

from common_schemas.enums import RiskLevel

from ....domain.entities.base_node import BaseNode
from ....domain.entities.node_definition import NodeDefinition
from ....domain.entities.node_metadata import NodeMetadata
from .._catalog_ns import _CATALOG_NS

_NODE_TYPE = "regex_replace"
_NODE_ID = uuid5(_CATALOG_NS, _NODE_TYPE)


@dataclass
class RegexReplaceInput:
    text: str
    pattern: str
    replacement: str
    max_count: int = 0   # 0 = 전체 교체
    ignore_case: bool = False


@dataclass
class RegexReplaceOutput:
    result: str
    replacements_made: int


class RegexReplaceNode(BaseNode[RegexReplaceInput, RegexReplaceOutput]):
    metadata = NodeMetadata(
        node_id=_NODE_ID,
        name="정규식 치환",
        category="transform",
        risk_level=RiskLevel.LOW,
        is_mvp=True,
    )
    input_schema = RegexReplaceInput
    output_schema = RegexReplaceOutput

    async def process(self, input: RegexReplaceInput) -> RegexReplaceOutput:
        flags = re.IGNORECASE if input.ignore_case else 0
        before_count = len(re.findall(input.pattern, input.text, flags))
        result = re.sub(input.pattern, input.replacement, input.text, count=input.max_count, flags=flags)
        after_count = len(re.findall(input.pattern, result, flags))
        return RegexReplaceOutput(result=result, replacements_made=before_count - after_count)


def get_node_definition() -> NodeDefinition:
    return NodeDefinition(
        node_id=_NODE_ID,
        node_type=_NODE_TYPE,
        name="정규식 치환",
        category="transform",
        version="1.0.0",
        input_schema={
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "pattern": {"type": "string"},
                "replacement": {"type": "string"},
                "max_count": {"type": "integer", "default": 0},
                "ignore_case": {"type": "boolean", "default": False},
            },
            "required": ["text", "pattern", "replacement"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "result": {"type": "string"},
                "replacements_made": {"type": "integer"},
            },
        },
        parameter_schema={},
        risk_level=RiskLevel.LOW,
        required_connections=[],
        description="정규식 패턴으로 텍스트 내 매칭 부분 치환",
        is_mvp=True,
        service_type=None,
    )
