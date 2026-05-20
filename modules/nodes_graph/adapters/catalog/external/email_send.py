from __future__ import annotations

import asyncio
import smtplib
import ssl
from dataclasses import dataclass
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
    body_type: str = "plain"                                    # plain | html
    use_tls: bool = True


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

        username: str | None = None
        password: str | None = None
        # credential 노드일 때 connection_token 형식은 'username:password' (SMTP 인증).
        if context.connection_token:
            if ":" not in context.connection_token:
                raise ValidationError("Email credential must be 'username:password' format")
            username, password = context.connection_token.split(":", 1)

        msg = MIMEMultipart("alternative")
        msg["Subject"] = input.subject
        msg["From"] = input.from_address
        msg["To"] = ", ".join(input.to_addresses)
        msg.attach(MIMEText(input.body, input.body_type))
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
                "smtp_host": {"type": "string"},
                "smtp_port": {"type": "integer", "default": 587},
                "from_address": {"type": "string"},
                "to_addresses": {"type": "array", "items": {"type": "string"}, "minItems": 1},
                "subject": {"type": "string"},
                "body": {"type": "string"},
                "body_type": {"type": "string", "enum": ["plain", "html"], "default": "plain"},
                "use_tls": {"type": "boolean", "default": True},
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
