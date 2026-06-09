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

_NODE_TYPE = "slack_read"
_NODE_ID = uuid5(_CATALOG_NS, _NODE_TYPE)
_SLACK_HISTORY_URL = "https://slack.com/api/conversations.history"
_TIMEOUT_SECONDS = 30


@dataclass
class SlackReadInput:
    channel: str                                    # 채널 ID (e.g. "C0123ABC")
    limit: int = 20                                 # 가져올 메시지 수 (최신순)
    oldest: str | None = None                       # 이 ts 이후 (포함 안 함)
    latest: str | None = None                       # 이 ts 이전


@dataclass
class SlackReadOutput:
    ok: bool
    messages: list[dict[str, Any]]                  # [{ts, user, text, type}]
    count: int
    raw_response: dict[str, Any]


class SlackReadNode(BaseNode[SlackReadInput, SlackReadOutput]):
    metadata = NodeMetadata(
        node_id=_NODE_ID,
        name="Slack 메시지 조회",
        category="integration",
        risk_level=RiskLevel.MEDIUM,
        is_mvp=True,
    )
    input_schema = SlackReadInput
    output_schema = SlackReadOutput

    async def process(self, input: SlackReadInput, context: NodeContext) -> SlackReadOutput:
        # connection_token = Slack Bot OAuth 토큰 (xoxb-...). conversations.history.
        if not context.connection_token:
            raise ValidationError("slack_read는 credential(Slack Bot 토큰)이 필요하다")

        params: dict[str, Any] = {"channel": input.channel, "limit": input.limit}
        if input.oldest:
            params["oldest"] = input.oldest
        if input.latest:
            params["latest"] = input.latest
        headers = {"Authorization": f"Bearer {context.connection_token}"}

        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            response = await client.get(_SLACK_HISTORY_URL, params=params, headers=headers)

        # Slack은 논리 오류도 HTTP 200 + {"ok": false, "error": ...}로 반환(slack_post_message 동일 계약).
        raw: dict[str, Any] = response.json()
        messages = [
            {
                "ts": m.get("ts", ""),
                "user": m.get("user", ""),
                "text": m.get("text", ""),
                "type": m.get("type", ""),
            }
            for m in raw.get("messages", [])
        ]
        return SlackReadOutput(
            ok=bool(raw.get("ok", False)),
            messages=messages,
            count=len(messages),
            raw_response=raw,
        )


def get_node_definition() -> NodeDefinition:
    return NodeDefinition(
        node_id=_NODE_ID,
        node_type=_NODE_TYPE,
        name="Slack 메시지 조회",
        category="integration",
        version="1.0.0",
        input_schema={
            "type": "object",
            "properties": {
                "channel": {"type": "string", "description": "채널 ID"},
                "limit": {"type": "integer", "default": 20},
                "oldest": {"type": ["string", "null"], "description": "이 ts 이후"},
                "latest": {"type": ["string", "null"], "description": "이 ts 이전"},
            },
            "required": ["channel"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "ok": {"type": "boolean"},
                "messages": {"type": "array", "items": {"type": "object"}},
                "count": {"type": "integer"},
                "raw_response": {"type": "object"},
            },
        },
        parameter_schema={},
        risk_level=RiskLevel.MEDIUM,
        required_connections=["slack"],
        description="Slack 채널 메시지 이력 조회 (conversations.history). OAuth 자격증명 필요",
        is_mvp=True,
        service_type="slack",
    )
