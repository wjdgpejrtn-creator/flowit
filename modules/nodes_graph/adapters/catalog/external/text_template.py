from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import uuid5

from common_schemas.enums import RiskLevel

from ....domain.entities.base_node import BaseNode
from ....domain.entities.node_definition import NodeDefinition
from ....domain.entities.node_metadata import NodeMetadata
from ....domain.catalog._catalog_ns import _CATALOG_NS

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

    async def process(self, input: TextTemplateInput) -> TextTemplateOutput:
        raise NotImplementedError(
            "텍스트 템플릿 렌더링은 REQ-005 toolset.TextTemplateTool을 통해 처리. "
            "execution_engine.ToolsetExecutor가 node_type 기반으로 toolset.execute_tool() 호출. "
            "BaseNode.process() 직접 호출 X."
        )


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
                "template": {"type": "string"},
                "variables": {"type": "object"},
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
