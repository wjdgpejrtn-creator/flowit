from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid5

from common_schemas.enums import RiskLevel

from ....domain.entities.base_node import BaseNode
from ....domain.entities.node_definition import NodeDefinition
from ....domain.entities.node_metadata import NodeMetadata
from ....domain.catalog._catalog_ns import _CATALOG_NS

_NODE_TYPE = "notion_create_page"
_NODE_ID = uuid5(_CATALOG_NS, _NODE_TYPE)


@dataclass
class NotionCreatePageInput:
    parent_id: str                                              # database_id 또는 page_id
    parent_type: str = "database_id"                            # database_id | page_id
    properties: dict[str, Any] = field(default_factory=dict)    # Notion properties (DB schema 준수)
    title: str | None = None                                    # parent_type=page_id일 때 title 속성
    content_blocks: list[dict[str, Any]] = field(default_factory=list)  # children blocks (paragraph/heading/...)
    icon_emoji: str | None = None


@dataclass
class NotionCreatePageOutput:
    page_id: str
    url: str
    created_time: str
    last_edited_time: str


class NotionCreatePageNode(BaseNode[NotionCreatePageInput, NotionCreatePageOutput]):
    metadata = NodeMetadata(
        node_id=_NODE_ID,
        name="Notion 페이지 생성",
        category="외부 API 연동",
        risk_level=RiskLevel.HIGH,
        is_mvp=True,
    )
    input_schema = NotionCreatePageInput
    output_schema = NotionCreatePageOutput

    async def process(self, input: NotionCreatePageInput) -> NotionCreatePageOutput:
        raise NotImplementedError(
            "Notion API 호출은 REQ-005 toolset connector를 통해 처리. "
            "Integration token 주입은 REQ-002 CredentialInjectionService 담당."
        )


def get_node_definition() -> NodeDefinition:
    return NodeDefinition(
        node_id=_NODE_ID,
        node_type=_NODE_TYPE,
        name="Notion 페이지 생성",
        category="외부 API 연동",
        version="1.0.0",
        input_schema={
            "type": "object",
            "properties": {
                "parent_id": {"type": "string"},
                "parent_type": {"type": "string", "enum": ["database_id", "page_id"], "default": "database_id"},
                "properties": {"type": "object"},
                "title": {"type": ["string", "null"]},
                "content_blocks": {"type": "array", "items": {"type": "object"}},
                "icon_emoji": {"type": ["string", "null"]},
            },
            "required": ["parent_id"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "page_id": {"type": "string"},
                "url": {"type": "string"},
                "created_time": {"type": "string"},
                "last_edited_time": {"type": "string"},
            },
        },
        parameter_schema={},
        risk_level=RiskLevel.HIGH,
        required_connections=["notion"],
        description="Notion 페이지 생성 (POST /v1/pages). Integration token 자격증명 필요",
        is_mvp=True,
        service_type="notion",
    )
