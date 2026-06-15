from __future__ import annotations

from dataclasses import dataclass
from string import Formatter
from typing import Any
from uuid import uuid5

from common_schemas import NodeContext
from common_schemas.enums import RiskLevel
from common_schemas.exceptions import ValidationError

from ....domain.catalog._catalog_ns import _CATALOG_NS
from ....domain.entities.base_node import BaseNode
from ....domain.entities.node_definition import NodeDefinition
from ....domain.entities.node_metadata import NodeMetadata

_NODE_TYPE = "text_template"
_NODE_ID = uuid5(_CATALOG_NS, _NODE_TYPE)


@dataclass
class TextTemplateInput:
    template: str
    variables: dict[str, Any]


@dataclass
class TextTemplateOutput:
    rendered: str


class TextTemplateNode(BaseNode[TextTemplateInput, TextTemplateOutput]):
    metadata = NodeMetadata(
        node_id=_NODE_ID,
        name="텍스트 템플릿",
        category="transform",
        risk_level=RiskLevel.LOW,
        is_mvp=True,
    )
    input_schema = TextTemplateInput
    output_schema = TextTemplateOutput

    async def process(self, input: TextTemplateInput, context: NodeContext) -> TextTemplateOutput:
        variables = input.variables or {}
        required_keys = {
            field_name for _, field_name, _, _ in Formatter().parse(input.template) if field_name is not None
        }
        missing = required_keys - variables.keys()
        if missing:
            raise ValidationError(f"Template variables missing: {sorted(missing)}")
        try:
            rendered = input.template.format_map(variables)
        except (KeyError, ValueError, IndexError) as e:
            raise ValidationError(f"Template rendering failed: {e}") from e
        return TextTemplateOutput(rendered=rendered)


def get_node_definition() -> NodeDefinition:
    return NodeDefinition(
        node_id=_NODE_ID,
        node_type=_NODE_TYPE,
        name="텍스트 템플릿",
        category="transform",
        version="1.0.0",
        input_schema={
            "type": "object",
            "properties": {
                "template": {
                    "type": "string",
                    "description": '{변수} 자리를 치환할 템플릿 문자열. 예: "안녕하세요 {name}님"',
                },
                "variables": {"type": "object", "description": '{변수}에 채워 넣을 값 객체. 예: {"name": "홍길동"}'},
            },
            "required": ["template", "variables"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "rendered": {"type": "string"},
            },
            "required": ["rendered"],
        },
        parameter_schema={},
        risk_level=RiskLevel.LOW,
        required_connections=[],
        description="Python str.format_map() 기반 텍스트 템플릿 렌더링. {variable} 문법 사용",
        is_mvp=True,
        service_type=None,
    )
