from __future__ import annotations

import base64
from dataclasses import dataclass, field
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any
from uuid import uuid5

import httpx
from common_schemas import NodeContext
from common_schemas.enums import RiskLevel
from common_schemas.exceptions import ExecutionError, ValidationError

from ....domain.catalog._catalog_ns import _CATALOG_NS
from ....domain.entities.base_node import BaseNode
from ....domain.entities.node_definition import NodeDefinition
from ....domain.entities.node_metadata import NodeMetadata

_NODE_TYPE = "gmail_send"
_NODE_ID = uuid5(_CATALOG_NS, _NODE_TYPE)
_GMAIL_SEND_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"
_TIMEOUT_SECONDS = 60


@dataclass
class GmailSendInput:
    to: list[str]  # 수신자 이메일 (1개 이상)
    subject: str
    body: str  # 메시지 본문 (text/html 둘 다 가능)
    cc: list[str] = field(default_factory=list)
    bcc: list[str] = field(default_factory=list)
    is_html: bool = False  # True이면 body를 text/html로 전송
    attachments: list[dict[str, Any]] = field(default_factory=list)  # [{"filename": ..., "content_base64": ...}]


@dataclass
class GmailSendOutput:
    message_id: str  # Gmail API 반환 메시지 ID
    thread_id: str
    label_ids: list[str]


class GmailSendNode(BaseNode[GmailSendInput, GmailSendOutput]):
    metadata = NodeMetadata(
        node_id=_NODE_ID,
        name="Gmail 메일 전송",
        category="action",
        risk_level=RiskLevel.HIGH,
        is_mvp=True,
    )
    input_schema = GmailSendInput
    output_schema = GmailSendOutput

    async def process(self, input: GmailSendInput, context: NodeContext) -> GmailSendOutput:
        # connection_token = Google OAuth access token. Gmail users.messages.send.
        if not context.connection_token:
            raise ValidationError("gmail_send는 credential(Google OAuth 토큰)이 필요하다")

        msg = MIMEMultipart()
        msg["To"] = ", ".join(input.to)
        msg["Subject"] = input.subject
        if input.cc:
            msg["Cc"] = ", ".join(input.cc)
        if input.bcc:
            msg["Bcc"] = ", ".join(input.bcc)
        msg.attach(MIMEText(input.body, "html" if input.is_html else "plain", "utf-8"))
        for att in input.attachments:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(base64.b64decode(att["content_base64"]))
            encoders.encode_base64(part)
            part.add_header("Content-Disposition", f'attachment; filename="{att.get("filename", "file")}"')
            msg.attach(part)

        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        headers = {
            "Authorization": f"Bearer {context.connection_token}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            response = await client.post(_GMAIL_SEND_URL, json={"raw": raw}, headers=headers)

        if response.status_code >= 400:
            raise ExecutionError(f"Gmail API 오류 {response.status_code}: {response.text[:200]}")

        data = response.json()
        return GmailSendOutput(
            message_id=data.get("id", ""),
            thread_id=data.get("threadId", ""),
            label_ids=data.get("labelIds", []),
        )


def get_node_definition() -> NodeDefinition:
    return NodeDefinition(
        node_id=_NODE_ID,
        node_type=_NODE_TYPE,
        name="Gmail 메일 전송",
        category="action",
        version="1.0.0",
        input_schema={
            "type": "object",
            "properties": {
                "to": {
                    "type": "array",
                    "items": {"type": "string", "format": "email"},
                    "minItems": 1,
                    "description": '받는 사람 이메일 주소 목록. 예: ["a@example.com"]',
                },
                "subject": {"type": "string", "description": "이메일 제목"},
                "body": {"type": "string", "description": "이메일 본문"},
                "cc": {
                    "type": "array",
                    "items": {"type": "string", "format": "email"},
                    "description": "참조(CC) 주소 목록(선택)",
                },
                "bcc": {
                    "type": "array",
                    "items": {"type": "string", "format": "email"},
                    "description": "숨은참조(BCC) 주소 목록(선택)",
                },
                "is_html": {
                    "type": "boolean",
                    "default": False,
                    "description": "본문을 HTML로 해석할지 여부. 기본값 false",
                },
                "attachments": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {"filename": {"type": "string"}, "content_base64": {"type": "string"}},
                    },
                    "description": "첨부파일 목록(선택)",
                },
            },
            "required": ["to", "subject", "body"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "message_id": {"type": "string"},
                "thread_id": {"type": "string"},
                "label_ids": {"type": "array", "items": {"type": "string"}},
            },
        },
        parameter_schema={},
        risk_level=RiskLevel.HIGH,
        required_connections=["google"],
        description="Gmail로 이메일 전송 (users.messages.send). Google OAuth 자격증명 필요",
        is_mvp=True,
        service_type="google_workspace",
    )
