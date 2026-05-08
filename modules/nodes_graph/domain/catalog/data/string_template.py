from __future__ import annotations

import string
from dataclasses import dataclass
from uuid import uuid5

from common_schemas.enums import RiskLevel

from ....domain.entities.base_node import BaseNode
from ....domain.entities.node_definition import NodeDefinition
from ....domain.entities.node_metadata import NodeMetadata
from .._catalog_ns import _CATALOG_NS

_NODE_TYPE = "string_template"
_NODE_ID = uuid5(_CATALOG_NS, _NODE_TYPE)


@dataclass
class StringTemplateInput:
    template: str                  # "안녕하세요, {name}님. 나이는 {age}세입니다."
    variables: dict[str, str]


@dataclass
class StringTemplateOutput:
    result: str


class StringTemplateNode(BaseNode[StringTemplateInput, StringTemplateOutput]):
    metadata = NodeMetadata(
        node_id=_NODE_ID,
        name="문자열 템플릿",
        category="데이터 처리",
        risk_level=RiskLevel.LOW,
        is_mvp=True,
    )
    input_schema = StringTemplateInput
    output_schema = StringTemplateOutput

    async def process(self, input: StringTemplateInput) -> StringTemplateOutput:
        result = string.Template(input.template).safe_substitute(input.variables)
        return StringTemplateOutput(result=result)


def get_node_definition() -> NodeDefinition:
    return NodeDefinition(
        node_id=_NODE_ID,
        node_type=_NODE_TYPE,
        name="문자열 템플릿",
        category="데이터 처리",
        version="1.0.0",
        input_schema={
            "type": "object",
            "properties": {
                "template": {"type": "string", "description": "예: '안녕하세요, ${name}님' (string.Template $변수명 형식)"},
                "variables": {"type": "object", "additionalProperties": {"type": "string"}},
            },
            "required": ["template", "variables"],
        },
        output_schema={
            "type": "object",
            "properties": {"result": {"type": "string"}},
        },
        parameter_schema={},
        risk_level=RiskLevel.LOW,
        required_connections=[],
        description="템플릿 문자열에 변수를 치환 ($변수명 형식, string.Template 사용으로 포맷 인젝션 차단)",
        is_mvp=True,
        service_type=None,
    )
