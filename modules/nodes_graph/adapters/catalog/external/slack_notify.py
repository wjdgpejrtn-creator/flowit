from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid5

from common_schemas.enums import RiskLevel

from ....domain.entities.base_node import BaseNode
from ....domain.entities.node_definition import NodeDefinition
from ....domain.entities.node_metadata import NodeMetadata
from ....domain.catalog._catalog_ns import _CATALOG_NS

_NODE_TYPE = "slack_notify"
_NODE_ID = uuid5(_CATALOG_NS, _NODE_TYPE)


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

    async def process(self, input: SlackNotifyInput) -> SlackNotifyOutput:
        raise NotImplementedError(
            "Slack 알림은 REQ-005 toolset.SlackNotifyTool을 통해 처리. "
            "execution_engine.ToolsetExecutor가 node_type 기반으로 toolset.execute_tool() 호출. "
            "BaseNode.process() 직접 호출 X."
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
                "message": {"type": "string"},
                "channel": {"type": "string"},
                "username": {"type": "string"},
                "icon_emoji": {"type": "string"},
                "timeout_seconds": {"type": "integer", "minimum": 1, "maximum": 30, "default": 10},
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
