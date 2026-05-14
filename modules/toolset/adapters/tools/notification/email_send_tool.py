from __future__ import annotations

import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

from common_schemas.enums import RiskLevel

from ....domain.base_tool import BaseTool
from ....domain.exceptions import ToolExecutionError


class EmailSendTool(BaseTool):
    name = "email_send"
    description = "이메일 발송 (SMTP, 비가역적)"
    version = "1.0.0"
    risk_level = RiskLevel.HIGH

    input_schema = {
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
    }

    output_schema = {
        "type": "object",
        "properties": {
            "sent": {"type": "boolean"},
            "recipients_count": {"type": "integer"},
        },
        "required": ["sent", "recipients_count"],
    }

    async def execute(self, input_data: dict[str, Any], **kwargs) -> dict[str, Any]:
        credential = kwargs.get("credential")

        host = input_data["smtp_host"]
        port = input_data.get("smtp_port", 587)
        from_addr = input_data["from_address"]
        to_addrs: list[str] = input_data["to_addresses"]
        subject = input_data["subject"]
        body = input_data["body"]
        body_type = input_data.get("body_type", "plain")
        use_tls = input_data.get("use_tls", True)

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = from_addr
        msg["To"] = ", ".join(to_addrs)
        msg.attach(MIMEText(body, body_type))

        username: str | None = None
        password: str | None = None
        if credential:
            if ":" not in credential.value:
                raise ToolExecutionError(
                    message="Email credential must be 'username:password' format",
                    code="TOOL_EXECUTION_ERROR",
                )
            username, password = credential.value.split(":", 1)

        try:
            context = ssl.create_default_context()
            with smtplib.SMTP(host, port, timeout=30) as server:
                if use_tls:
                    server.starttls(context=context)
                if username and password:
                    server.login(username, password)
                server.sendmail(from_addr, to_addrs, msg.as_string())

            return {"sent": True, "recipients_count": len(to_addrs)}

        except smtplib.SMTPException as e:
            raise ToolExecutionError(message=f"Email send failed: {e}", code="TOOL_EXECUTION_ERROR") from e
        except OSError as e:
            raise ToolExecutionError(message=f"SMTP connection to '{host}:{port}' failed: {e}", code="TOOL_EXECUTION_ERROR") from e
