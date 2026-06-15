from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid5

from common_schemas import NodeContext
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
        category="trigger",
        risk_level=RiskLevel.LOW,
        is_mvp=True,
    )
    input_schema = WebhookTriggerInput
    output_schema = WebhookTriggerOutput

    async def process(self, input: WebhookTriggerInput, context: NodeContext) -> WebhookTriggerOutput:
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
        category="trigger",
        version="1.0.0",
        input_schema={
            "type": "object",
            "properties": {
                "payload": {
                    "type": "object",
                    "description": "수신한 웹훅 본문(실행 엔진이 주입). 테스트 시 예상 페이로드 입력",
                },
                "headers": {"type": "object", "description": "수신한 HTTP 헤더(실행 엔진이 주입)"},
                "method": {"type": "string", "default": "POST", "description": "허용할 HTTP 메서드. 기본값 POST"},
                "path": {"type": "string", "description": '웹훅을 수신할 경로. 예: "/hooks/order-created"'},
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
