from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid5

from common_schemas.enums import RiskLevel

from ....domain.entities.base_node import BaseNode
from ....domain.entities.node_definition import NodeDefinition
from ....domain.entities.node_metadata import NodeMetadata
from .._catalog_ns import _CATALOG_NS

_NODE_TYPE = "webhook_trigger"
_NODE_ID = uuid5(_CATALOG_NS, _NODE_TYPE)


@dataclass
class WebhookTriggerInput:
    payload: dict[str, Any]
    headers: dict[str, str] = field(default_factory=dict)
    method: str = "POST"
    path: str = ""


@dataclass
class WebhookTriggerOutput:
    payload: dict[str, Any]
    headers: dict[str, str]
    method: str
    path: str


class WebhookTriggerNode(BaseNode[WebhookTriggerInput, WebhookTriggerOutput]):
    metadata = NodeMetadata(
        node_id=_NODE_ID,
        name="웹훅 트리거",
        category="트리거",
        risk_level=RiskLevel.LOW,
        is_mvp=True,
    )
    input_schema = WebhookTriggerInput
    output_schema = WebhookTriggerOutput

    async def process(self, input: WebhookTriggerInput) -> WebhookTriggerOutput:
        return WebhookTriggerOutput(
            payload=input.payload,
            headers=input.headers,
            method=input.method,
            path=input.path,
        )


def get_node_definition() -> NodeDefinition:
    return NodeDefinition(
        node_id=_NODE_ID,
        node_type=_NODE_TYPE,
        name="웹훅 트리거",
        category="트리거",
        version="1.0.0",
        input_schema={
            "type": "object",
            "properties": {
                "payload": {"type": "object"},
                "headers": {"type": "object"},
                "method": {"type": "string", "default": "POST"},
                "path": {"type": "string"},
            },
            "required": ["payload"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "payload": {"type": "object"},
                "headers": {"type": "object"},
                "method": {"type": "string"},
                "path": {"type": "string"},
            },
        },
        parameter_schema={},
        risk_level=RiskLevel.LOW,
        required_connections=[],
        description="외부 HTTP 웹훅 수신. 실행 엔진이 엔드포인트를 등록하고 페이로드를 주입",
        is_mvp=True,
        service_type=None,
    )
