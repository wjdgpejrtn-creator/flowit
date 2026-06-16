from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass, field
from email.mime.application import MIMEApplication
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
            self._attach_file(msg, att)

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

    @staticmethod
    def _attach_file(msg: MIMEMultipart, att: dict | str) -> None:
        """첨부 1건을 메시지에 추가. content_base64는 상류 산출물 ${...} 참조 해소 결과(base64).

        정규형은 ``{"filename", "content_base64", "mimetype"}`` dict. 견고성을 위해 **bare
        문자열**(LLM이 attachments=["${...}"]로 채운 경우 런타임 해소 시 base64 문자열)도 허용한다.
        content가 없거나 base64 디코드 실패면 명확한 ValidationError(조용한 누락·KeyError/디코드
        크래시 방지 — email_send._attach_file와 동일 계약, PR #537 견고화를 gmail_send에도 적용).
        """
        if isinstance(att, str):
            att = {"content_base64": att}
        content = att.get("content_base64")
        if not content:
            raise ValidationError("gmail_send attachment에 content_base64가 없습니다")
        try:
            raw = base64.b64decode(content, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValidationError(f"gmail_send attachment content가 유효한 base64가 아닙니다: {exc}")
        mimetype = att.get("mimetype") or "application/octet-stream"
        _, _, subtype = mimetype.partition("/")
        part = MIMEApplication(raw, _subtype=subtype or "octet-stream")
        part.add_header(
            "Content-Disposition", "attachment", filename=att.get("filename") or "attachment"
        )
        msg.attach(part)


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
                        "properties": {
                            "filename": {"type": "string", "description": "첨부 파일명. 예: report.pdf"},
                            "content_base64": {
                                "type": "string",
                                "description": "base64 인코딩 파일 내용(상류 산출물 ${...} 참조)",
                            },
                            "mimetype": {"type": "string", "description": "MIME 타입(선택). 예: application/pdf"},
                        },
                        "required": ["content_base64"],
                    },
                    "description": (
                        "첨부 파일 목록(선택). 상류 산출물을 첨부하려면 content_base64에 그 출력 참조를 둔다. "
                        '예: PDF 첨부 = [{"filename": "report.pdf", "content_base64": '
                        '"${<pdf_generate instance_id>.pdf_bytes}", "mimetype": "application/pdf"}]'
                    ),
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
