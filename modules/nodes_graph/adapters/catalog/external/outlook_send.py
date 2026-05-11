from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid5

from common_schemas.enums import RiskLevel

from ....domain.entities.base_node import BaseNode
from ....domain.entities.node_definition import NodeDefinition
from ....domain.entities.node_metadata import NodeMetadata
from ....domain.catalog._catalog_ns import _CATALOG_NS

_NODE_TYPE = "outlook_send"
_NODE_ID = uuid5(_CATALOG_NS, _NODE_TYPE)


@dataclass
class OutlookSendInput:
    to: list[str]
    subject: str
    body: str
    cc: list[str] = field(default_factory=list)
    bcc: list[str] = field(default_factory=list)
    is_html: bool = False
    attachments: list[dict[str, Any]] = field(default_factory=list)
    save_to_sent_items: bool = True


@dataclass
class OutlookSendOutput:
    message_id: str                                 # Microsoft Graph 반환 메시지 ID
    conversation_id: str
    web_link: str


class OutlookSendNode(BaseNode[OutlookSendInput, OutlookSendOutput]):
    metadata = NodeMetadata(
        node_id=_NODE_ID,
        name="Outlook 메일 전송",
        category="커뮤니케이션",
        risk_level=RiskLevel.HIGH,
        is_mvp=True,
    )
    input_schema = OutlookSendInput
    output_schema = OutlookSendOutput

    async def process(self, input: OutlookSendInput) -> OutlookSendOutput:
        raise NotImplementedError(
            "외부 서비스 호출은 REQ-005 toolset connector를 통해 처리. "
            "OAuth credential 주입은 REQ-002 CredentialInjectionService 담당."
        )


def get_node_definition() -> NodeDefinition:
    return NodeDefinition(
        node_id=_NODE_ID,
        node_type=_NODE_TYPE,
        name="Outlook 메일 전송",
        category="커뮤니케이션",
        version="1.0.0",
        input_schema={
            "type": "object",
            "properties": {
                "to": {"type": "array", "items": {"type": "string", "format": "email"}, "minItems": 1},
                "subject": {"type": "string"},
                "body": {"type": "string"},
                "cc": {"type": "array", "items": {"type": "string", "format": "email"}},
                "bcc": {"type": "array", "items": {"type": "string", "format": "email"}},
                "is_html": {"type": "boolean", "default": False},
                "attachments": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "filename": {"type": "string"},
                            "content_base64": {"type": "string"},
                        },
                    },
                },
                "save_to_sent_items": {"type": "boolean", "default": True},
            },
            "required": ["to", "subject", "body"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "message_id": {"type": "string"},
                "conversation_id": {"type": "string"},
                "web_link": {"type": "string"},
            },
        },
        parameter_schema={},
        risk_level=RiskLevel.HIGH,
        required_connections=["microsoft"],
        description="Outlook으로 이메일 전송 (Microsoft Graph /sendMail). Microsoft OAuth 자격증명 필요",
        is_mvp=True,
        service_type="microsoft_365",
    )
