from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import uuid5

import httpx
from common_schemas import NodeContext
from common_schemas.enums import RiskLevel
from common_schemas.exceptions import ValidationError

from ....domain.catalog._catalog_ns import _CATALOG_NS
from ....domain.entities.base_node import BaseNode
from ....domain.entities.node_definition import NodeDefinition
from ....domain.entities.node_metadata import NodeMetadata
from ._url_guard import validate_outbound_url

_NODE_TYPE = "slack_notify"
_NODE_ID = uuid5(_CATALOG_NS, _NODE_TYPE)
_MAX_TIMEOUT_SECONDS = 30  # input_schema의 timeout_seconds maximum과 정합


@dataclass
class SlackNotifyInput:
    message: str
    channel: str | None = None
    username: str | None = None
    icon_emoji: str | None = None
    timeout_seconds: int = 10


@dataclass
class SlackNotifyOutput:
    sent: bool
    status_code: int


class SlackNotifyNode(BaseNode[SlackNotifyInput, SlackNotifyOutput]):
    metadata = NodeMetadata(
        node_id=_NODE_ID,
        name="Slack 알림",
        category="action",
        risk_level=RiskLevel.HIGH,
        is_mvp=True,
    )
    input_schema = SlackNotifyInput
    output_schema = SlackNotifyOutput

    async def process(self, input: SlackNotifyInput, context: NodeContext) -> SlackNotifyOutput:
        # connection_token = Slack Incoming Webhook URL (credential.value).
        webhook_url = context.connection_token
        if not webhook_url:
            raise ValidationError("slack_notify는 credential(Slack Incoming Webhook URL)이 필요하다")
        await validate_outbound_url(webhook_url)

        payload: dict[str, Any] = {"text": input.message}
        for key in ("channel", "username", "icon_emoji"):
            value = getattr(input, key)
            if value:
                payload[key] = value

        timeout = min(input.timeout_seconds, _MAX_TIMEOUT_SECONDS)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(webhook_url, json=payload)

        return SlackNotifyOutput(
            sent=response.status_code == 200,
            status_code=response.status_code,
        )


def get_node_definition() -> NodeDefinition:
    return NodeDefinition(
        node_id=_NODE_ID,
        node_type=_NODE_TYPE,
        name="Slack 알림",
        category="action",
        version="1.0.0",
        input_schema={
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "전송할 메시지 텍스트"},
                "channel": {
                    "type": "string",
                    "description": '전송할 채널(선택). Webhook에 기본 채널이 설정돼 있으면 생략 가능. 예: "#general"',
                },
                "username": {"type": "string", "description": "메시지를 보낼 표시 이름(선택)"},
                "icon_emoji": {"type": "string", "description": '봇 아이콘 이모지(선택). 예: ":robot_face:"'},
                "timeout_seconds": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 30,
                    "default": 10,
                    "description": "전송 대기 제한 시간(초). 기본값 10",
                },
            },
            "required": ["message"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "sent": {"type": "boolean"},
                "status_code": {"type": "integer"},
            },
            "required": ["sent", "status_code"],
        },
        parameter_schema={},
        risk_level=RiskLevel.HIGH,
        required_connections=["slack"],
        description="Slack Incoming Webhook으로 메시지 전송. Webhook URL은 credential.value로 주입",
        is_mvp=True,
        service_type="slack",
    )
