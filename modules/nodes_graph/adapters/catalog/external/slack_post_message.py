from __future__ import annotations

from dataclasses import dataclass, field
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

_NODE_TYPE = "slack_post_message"
_NODE_ID = uuid5(_CATALOG_NS, _NODE_TYPE)
_SLACK_POST_MESSAGE_URL = "https://slack.com/api/chat.postMessage"
_TIMEOUT_SECONDS = 30


@dataclass
class SlackPostMessageInput:
    channel: str  # 채널 ID 또는 채널명 (e.g. "C0123ABC", "#general")
    text: str  # 메시지 본문
    thread_ts: str | None = None  # 스레드 답글일 경우 부모 메시지 ts
    mrkdwn: bool = True  # Slack mrkdwn 포맷 활성화
    blocks: list[dict[str, Any]] = field(default_factory=list)  # Block Kit (선택)


@dataclass
class SlackPostMessageOutput:
    ok: bool
    ts: str  # 게시된 메시지 timestamp (ID 역할)
    channel: str  # 해석된 채널 ID
    raw_response: dict[str, Any]


class SlackPostMessageNode(BaseNode[SlackPostMessageInput, SlackPostMessageOutput]):
    metadata = NodeMetadata(
        node_id=_NODE_ID,
        name="Slack 메시지 전송",
        category="action",
        risk_level=RiskLevel.HIGH,
        is_mvp=True,
    )
    input_schema = SlackPostMessageInput
    output_schema = SlackPostMessageOutput

    async def process(self, input: SlackPostMessageInput, context: NodeContext) -> SlackPostMessageOutput:
        # connection_token = Slack Bot OAuth 토큰 (xoxb-...).
        if not context.connection_token:
            raise ValidationError("slack_post_message는 credential(Slack Bot 토큰)이 필요하다")

        payload: dict[str, Any] = {
            "channel": input.channel,
            "text": input.text,
            "mrkdwn": input.mrkdwn,
        }
        if input.thread_ts:
            payload["thread_ts"] = input.thread_ts
        if input.blocks:
            payload["blocks"] = input.blocks
        headers = {
            "Authorization": f"Bearer {context.connection_token}",
            "Content-Type": "application/json; charset=utf-8",
        }

        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            response = await client.post(_SLACK_POST_MESSAGE_URL, json=payload, headers=headers)

        # chat.postMessage는 논리 오류도 HTTP 200 + {"ok": false, "error": ...}로 반환한다.
        # 이를 ok=False로 조용히 통과시키면 not_in_channel(봇 미초대) 같은 미전송이 "성공"처럼
        # 보여 디버깅을 가린다 — Google 노드(HTTP 4xx raise)와 동일하게 실패를 노드 실패로
        # 노출한다. (HIGH risk 부수효과 노드라 미전송은 조용한 no-op이 아니라 실패여야 한다.)
        raw: dict[str, Any] = response.json()
        if not raw.get("ok", False):
            raise ExecutionError(f"Slack chat.postMessage 오류: {raw.get('error', 'unknown')}")
        return SlackPostMessageOutput(
            ok=bool(raw.get("ok", False)),
            ts=raw.get("ts", ""),
            channel=raw.get("channel", ""),
            raw_response=raw,
        )


def get_node_definition() -> NodeDefinition:
    return NodeDefinition(
        node_id=_NODE_ID,
        node_type=_NODE_TYPE,
        name="Slack 메시지 전송",
        category="action",
        version="1.0.0",
        input_schema={
            "type": "object",
            "properties": {
                "channel": {"type": "string", "description": "채널 ID 또는 채널명"},
                "text": {"type": "string", "description": "메시지 본문"},
                "thread_ts": {"type": ["string", "null"], "description": "스레드 부모 메시지 ts"},
                "mrkdwn": {
                    "type": "boolean",
                    "default": True,
                    "description": "Slack 마크다운(*굵게*, _기울임_ 등) 해석 여부. 기본값 true",
                },
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
