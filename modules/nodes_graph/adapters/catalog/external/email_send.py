from __future__ import annotations

import asyncio
import base64
import binascii
import smtplib
import ssl
from dataclasses import dataclass, field
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from uuid import uuid5

from common_schemas import NodeContext
from common_schemas.enums import RiskLevel
from common_schemas.exceptions import ValidationError

from ....domain.catalog._catalog_ns import _CATALOG_NS
from ....domain.entities.base_node import BaseNode
from ....domain.entities.node_definition import NodeDefinition
from ....domain.entities.node_metadata import NodeMetadata
from ._url_guard import validate_outbound_host

_NODE_TYPE = "email_send"
_NODE_ID = uuid5(_CATALOG_NS, _NODE_TYPE)


@dataclass
class EmailSendInput:
    smtp_host: str
    from_address: str
    to_addresses: list[str]
    subject: str
    body: str
    smtp_port: int = 587
    body_type: str = "plain"  # plain | html
    use_tls: bool = True
    # 첨부 파일 목록. 각 항목: {"filename": str, "content_base64": str, "mimetype": "a/b"(선택)}.
    # 상류 산출물(예: pdf_generate.pdf_bytes)을 ${...} 참조로 content_base64에 받아 첨부한다.
    # 키 이름은 gmail_send와 정합(content_base64) — 드래프터 배선이 두 발송 노드 공통.
    attachments: list[dict] = field(default_factory=list)


@dataclass
class EmailSendOutput:
    sent: bool
    recipients_count: int


class EmailSendNode(BaseNode[EmailSendInput, EmailSendOutput]):
    metadata = NodeMetadata(
        node_id=_NODE_ID,
        name="이메일 발송",
        category="action",
        risk_level=RiskLevel.HIGH,
        is_mvp=True,
    )
    input_schema = EmailSendInput
    output_schema = EmailSendOutput

    async def process(self, input: EmailSendInput, context: NodeContext) -> EmailSendOutput:
        if not input.to_addresses:
            raise ValidationError("email_send requires at least one recipient")
        # SSRF — smtp_host가 내부/예약 대역이면 차단 (slack_notify 웹훅 가드와 대칭).
        await validate_outbound_host(input.smtp_host, input.smtp_port)

        username: str | None = None
        password: str | None = None
        # credential 노드일 때 connection_token 형식은 'username:password' (SMTP 인증).
        if context.connection_token:
            if ":" not in context.connection_token:
                raise ValidationError("Email credential must be 'username:password' format")
            username, password = context.connection_token.split(":", 1)

        # 첨부가 있으면 "mixed"(본문+파일), 없으면 기존 "alternative" 유지(회귀 0).
        msg = MIMEMultipart("mixed" if input.attachments else "alternative")
        msg["Subject"] = input.subject
        msg["From"] = input.from_address
        msg["To"] = ", ".join(input.to_addresses)
        msg.attach(MIMEText(input.body, input.body_type))
        for att in input.attachments:
            self._attach_file(msg, att)
        message = msg.as_string()

        def _send_sync() -> None:
            tls_context = ssl.create_default_context()
            with smtplib.SMTP(input.smtp_host, input.smtp_port, timeout=30) as server:
                if input.use_tls:
                    server.starttls(context=tls_context)
                if username and password:
                    server.login(username, password)
                server.sendmail(input.from_address, input.to_addresses, message)

        # smtplib는 blocking — 노드 실행 1회분 이벤트 루프를 막지 않도록 스레드로 분리.
        await asyncio.to_thread(_send_sync)
        return EmailSendOutput(sent=True, recipients_count=len(input.to_addresses))

    @staticmethod
    def _attach_file(msg: MIMEMultipart, att: dict) -> None:
        """첨부 1건을 메시지에 추가. content는 base64 문자열(상류 산출물 ${...} 참조 결과).

        필수 키: ``content``(base64). ``filename`` 미지정 시 'attachment'. ``mimetype``는
        'maintype/subtype' 형식(미지정 시 application/octet-stream). content가 비었거나
        base64 디코드 실패면 ValidationError(조용한 누락 방지 — 첨부 의도가 명시됐는데 빠지면
        QA·사용자 기대와 어긋남).
        """
        content = att.get("content_base64")
        if not content:
            raise ValidationError("email_send attachment에 content_base64가 없습니다")
        try:
            raw = base64.b64decode(content, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValidationError(f"email_send attachment content가 유효한 base64가 아닙니다: {exc}")
        mimetype = att.get("mimetype") or "application/octet-stream"
        maintype, _, subtype = mimetype.partition("/")
        part = MIMEApplication(raw, _subtype=subtype or "octet-stream")
        part.add_header(
            "Content-Disposition", "attachment", filename=att.get("filename") or "attachment"
        )
        msg.attach(part)


def get_node_definition() -> NodeDefinition:
    return NodeDefinition(
        node_id=_NODE_ID,
        node_type=_NODE_TYPE,
        name="이메일 발송",
        category="action",
        version="1.0.0",
        input_schema={
            "type": "object",
            "properties": {
                "smtp_host": {"type": "string", "description": 'SMTP 서버 주소. 예: "smtp.gmail.com"'},
                "smtp_port": {"type": "integer", "default": 587, "description": "SMTP 포트. 기본값 587(TLS)"},
                "from_address": {"type": "string", "description": "보내는 사람 이메일 주소"},
                "to_addresses": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 1,
                    "description": '받는 사람 이메일 주소 목록. 예: ["a@example.com"]',
                },
                "subject": {"type": "string", "description": "이메일 제목"},
                "body": {"type": "string", "description": "이메일 본문"},
                "body_type": {
                    "type": "string",
                    "enum": ["plain", "html"],
                    "default": "plain",
                    "description": "본문 형식. plain=일반텍스트, html=HTML. 기본값 plain",
                },
                "use_tls": {"type": "boolean", "default": True, "description": "TLS 암호화 사용 여부. 기본값 true"},
                "attachments": {
                    "type": "array",
                    "description": (
                        "첨부 파일 목록(선택). 상류 산출물을 첨부하려면 content_base64에 그 출력 참조를 둔다. "
                        '예: PDF 첨부 = [{"filename": "report.pdf", "content_base64": "${<pdf_generate instance_id>.pdf_bytes}", "mimetype": "application/pdf"}]'
                    ),
                    "items": {
                        "type": "object",
                        "properties": {
                            "filename": {"type": "string", "description": "첨부 파일명. 예: report.pdf"},
                            "content_base64": {"type": "string", "description": "base64 인코딩 파일 내용(상류 산출물 ${...} 참조)"},
                            "mimetype": {"type": "string", "description": 'MIME 타입. 예: "application/pdf"'},
                        },
                        "required": ["content_base64"],
                    },
                },
            },
            "required": ["smtp_host", "from_address", "to_addresses", "subject", "body"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "sent": {"type": "boolean"},
                "recipients_count": {"type": "integer"},
            },
            "required": ["sent", "recipients_count"],
        },
        parameter_schema={},
        risk_level=RiskLevel.HIGH,
        required_connections=[],
        description="SMTP 이메일 발송 (비가역적). credential.value 형식: 'username:password'",
        is_mvp=True,
        service_type=None,
    )
