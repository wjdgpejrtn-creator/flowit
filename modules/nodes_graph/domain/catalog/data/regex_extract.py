from __future__ import annotations

import re
from dataclasses import dataclass
from uuid import uuid5

from common_schemas.enums import RiskLevel

from ....domain.entities.base_node import BaseNode
from ....domain.entities.node_definition import NodeDefinition
from ....domain.entities.node_metadata import NodeMetadata
from .._catalog_ns import _CATALOG_NS

_NODE_TYPE = "regex_extract"
_NODE_ID = uuid5(_CATALOG_NS, _NODE_TYPE)


@dataclass
class RegexExtractInput:
    text: str
    pattern: str
    ignore_case: bool = False
    multiline: bool = False


@dataclass
class RegexExtractOutput:
    matches: list[str]
    groups: list[list[str]]
    count: int
    first_match: str


class RegexExtractNode(BaseNode[RegexExtractInput, RegexExtractOutput]):
    metadata = NodeMetadata(
        node_id=_NODE_ID,
        name="정규식 추출",
        category="데이터 처리",
        risk_level=RiskLevel.LOW,
        is_mvp=True,
    )
    input_schema = RegexExtractInput
    output_schema = RegexExtractOutput

    async def process(self, input: RegexExtractInput) -> RegexExtractOutput:
        flags = 0
        if input.ignore_case:
            flags |= re.IGNORECASE
        if input.multiline:
            flags |= re.MULTILINE
        compiled = re.compile(input.pattern, flags)
        found = compiled.finditer(input.text)
        matches = []
        groups = []
        for m in found:
            matches.append(m.group(0))
            groups.append(list(m.groups()))
        return RegexExtractOutput(
            matches=matches,
            groups=groups,
            count=len(matches),
            first_match=matches[0] if matches else "",
        )


def get_node_definition() -> NodeDefinition:
    return NodeDefinition(
        node_id=_NODE_ID,
        node_type=_NODE_TYPE,
        name="정규식 추출",
        category="데이터 처리",
        version="1.0.0",
        input_schema={
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "pattern": {"type": "string"},
                "ignore_case": {"type": "boolean", "default": False},
                "multiline": {"type": "boolean", "default": False},
            },
            "required": ["text", "pattern"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "matches": {"type": "array", "items": {"type": "string"}},
                "groups": {"type": "array"},
                "count": {"type": "integer"},
                "first_match": {"type": "string"},
            },
        },
        parameter_schema={},
        risk_level=RiskLevel.LOW,
        required_connections=[],
        description="정규식 패턴으로 텍스트에서 매칭 값 추출",
        is_mvp=True,
        service_type=None,
    )
