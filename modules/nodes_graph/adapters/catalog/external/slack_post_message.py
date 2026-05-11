from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid5

from common_schemas.enums import RiskLevel

from ....domain.entities.base_node import BaseNode
from ....domain.entities.node_definition import NodeDefinition
from ....domain.entities.node_metadata import NodeMetadata
from ....domain.catalog._catalog_ns import _CATALOG_NS

_NODE_TYPE = "slack_post_message"
_NODE_ID = uuid5(_CATALOG_NS, _NODE_TYPE)


@dataclass
class SlackPostMessageInput:
    channel: str                                    # 채널 ID 또는 채널명 (e.g. "C0123ABC", "#general")
    text: str                                       # 메시지 본문
    thread_ts: str | None = None                    # 스레드 답글일 경우 부모 메시지 ts
    mrkdwn: bool = True                             # Slack mrkdwn 포맷 활성화
    blocks: list[dict[str, Any]] = field(default_factory=list)  # Block Kit (선택)


@dataclass
class SlackPostMessageOutput:
    ok: bool
    ts: str                                         # 게시된 메시지 timestamp (ID 역할)
    channel: str                                    # 해석된 채널 ID
    raw_response: dict[str, Any]


class SlackPostMessageNode(BaseNode[SlackPostMessageInput, SlackPostMessageOutput]):
    metadata = NodeMetadata(
        node_id=_NODE_ID,
        name="Slack 메시지 전송",
        category="커뮤니케이션",
        risk_level=RiskLevel.HIGH,
        is_mvp=True,
    )
    input_schema = SlackPostMessageInput
    output_schema = SlackPostMessageOutput

    async def process(self, input: SlackPostMessageInput) -> SlackPostMessageOutput:
        raise NotImplementedError(
            "외부 서비스 호출은 REQ-005 toolset connector를 통해 처리. "
            "OAuth credential 주입은 REQ-002 CredentialInjectionService 담당."
        )


def get_node_definition() -> NodeDefinition:
    return NodeDefinition(
        node_id=_NODE_ID,
        node_type=_NODE_TYPE,
        name="Slack 메시지 전송",
        category="커뮤니케이션",
        version="1.0.0",
        input_schema={
            "type": "object",
            "properties": {
                "channel": {"type": "string", "description": "채널 ID 또는 채널명"},
                "text": {"type": "string", "description": "메시지 본문"},
                "thread_ts": {"type": ["string", "null"], "description": "스레드 부모 메시지 ts"},
                "mrkdwn": {"type": "boolean", "default": True},
                "blocks": {"type": "array", "items": {"type": "object"}, "description": "Slack Block Kit"},
            },
            "required": ["channel", "text"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "ok": {"type": "boolean"},
                "ts": {"type": "string"},
                "channel": {"type": "string"},
                "raw_response": {"type": "object"},
            },
        },
        parameter_schema={},
        risk_level=RiskLevel.HIGH,
        required_connections=["slack"],
        description="Slack 채널에 메시지 전송 (chat.postMessage). OAuth 자격증명 필요",
        is_mvp=True,
        service_type="slack",
    )
