from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid5

import httpx
from common_schemas import NodeContext
from common_schemas.enums import RiskLevel

from ....domain.catalog._catalog_ns import _CATALOG_NS
from ....domain.entities.base_node import BaseNode
from ....domain.entities.node_definition import NodeDefinition
from ....domain.entities.node_metadata import NodeMetadata

_NODE_TYPE = "webhook"
_NODE_ID = uuid5(_CATALOG_NS, _NODE_TYPE)


@dataclass
class WebhookInput:
    url: str
    payload: dict[str, Any]
    headers: dict[str, str] = field(default_factory=dict)
    secret: str | None = None
    timeout_seconds: int = 10


@dataclass
class WebhookOutput:
    status_code: int
    delivered: bool


class WebhookNode(BaseNode[WebhookInput, WebhookOutput]):
    metadata = NodeMetadata(
        node_id=_NODE_ID,
        name="웹훅 발송",
        category="action",
        risk_level=RiskLevel.HIGH,
        is_mvp=True,
    )
    input_schema = WebhookInput
    output_schema = WebhookOutput

    async def process(self, input: WebhookInput, context: NodeContext) -> WebhookOutput:
        headers = {"Content-Type": "application/json", **input.headers}
        body_bytes = json.dumps(input.payload).encode()

        if input.secret:
            signature = hmac.new(input.secret.encode(), body_bytes, hashlib.sha256).hexdigest()
            headers["X-Webhook-Signature"] = f"sha256={signature}"

        async with httpx.AsyncClient(timeout=input.timeout_seconds) as client:
            response = await client.post(input.url, content=body_bytes, headers=headers)

        return WebhookOutput(
            status_code=response.status_code,
            delivered=response.status_code < 300,
        )


def get_node_definition() -> NodeDefinition:
    return NodeDefinition(
        node_id=_NODE_ID,
        node_type=_NODE_TYPE,
        name="웹훅 발송",
        category="action",
        version="1.0.0",
        input_schema={
            "type": "object",
            "properties": {
                "url": {"type": "string"},
                "payload": {"type": "object"},
                "headers": {"type": "object"},
                "secret": {"type": "string"},
                "timeout_seconds": {"type": "integer", "minimum": 1, "maximum": 60, "default": 10},
            },
            "required": ["url", "payload"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "status_code": {"type": "integer"},
                "delivered": {"type": "boolean"},
            },
            "required": ["status_code", "delivered"],
        },
        parameter_schema={},
        risk_level=RiskLevel.HIGH,
        required_connections=[],
        description="웹훅 발송 (fire-and-forget). secret 제공 시 HMAC-SHA256 서명 헤더 자동 추가",
        is_mvp=True,
        service_type=None,
    )
