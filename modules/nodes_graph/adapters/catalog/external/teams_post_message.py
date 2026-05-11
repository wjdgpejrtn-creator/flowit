from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid5

from common_schemas.enums import RiskLevel

from ....domain.entities.base_node import BaseNode
from ....domain.entities.node_definition import NodeDefinition
from ....domain.entities.node_metadata import NodeMetadata
from ....domain.catalog._catalog_ns import _CATALOG_NS

_NODE_TYPE = "teams_post_message"
_NODE_ID = uuid5(_CATALOG_NS, _NODE_TYPE)


@dataclass
class TeamsPostMessageInput:
    team_id: str                                    # 팀 ID
    channel_id: str                                 # 채널 ID
    content: str                                    # 메시지 본문
    content_type: str = "text"                      # "text" | "html"
    subject: str | None = None                      # 메시지 제목 (선택)
    mentions: list[dict[str, Any]] = field(default_factory=list)  # [{"id": "...", "displayName": "..."}]


@dataclass
class TeamsPostMessageOutput:
    message_id: str                                 # Graph API 반환 메시지 ID
    web_url: str
    created_datetime: str


class TeamsPostMessageNode(BaseNode[TeamsPostMessageInput, TeamsPostMessageOutput]):
    metadata = NodeMetadata(
        node_id=_NODE_ID,
        name="Teams 메시지 전송",
        category="커뮤니케이션",
        risk_level=RiskLevel.HIGH,
        is_mvp=True,
    )
    input_schema = TeamsPostMessageInput
    output_schema = TeamsPostMessageOutput

    async def process(self, input: TeamsPostMessageInput) -> TeamsPostMessageOutput:
        raise NotImplementedError(
            "외부 서비스 호출은 REQ-005 toolset connector를 통해 처리. "
            "OAuth credential 주입은 REQ-002 CredentialInjectionService 담당."
        )


def get_node_definition() -> NodeDefinition:
    return NodeDefinition(
        node_id=_NODE_ID,
        node_type=_NODE_TYPE,
        name="Teams 메시지 전송",
        category="커뮤니케이션",
        version="1.0.0",
        input_schema={
            "type": "object",
            "properties": {
                "team_id": {"type": "string"},
                "channel_id": {"type": "string"},
                "content": {"type": "string"},
                "content_type": {"type": "string", "enum": ["text", "html"], "default": "text"},
                "subject": {"type": ["string", "null"]},
                "mentions": {"type": "array", "items": {"type": "object"}},
            },
            "required": ["team_id", "channel_id", "content"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "message_id": {"type": "string"},
                "web_url": {"type": "string"},
                "created_datetime": {"type": "string"},
            },
        },
        parameter_schema={},
        risk_level=RiskLevel.HIGH,
        required_connections=["microsoft"],
        description="Microsoft Teams 채널에 메시지 전송 (Graph /teams/{id}/channels/{id}/messages). Microsoft OAuth 자격증명 필요",
        is_mvp=True,
        service_type="microsoft_365",
    )
