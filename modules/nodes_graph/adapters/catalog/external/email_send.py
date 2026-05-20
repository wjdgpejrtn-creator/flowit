from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid5

from common_schemas import NodeContext
from common_schemas.enums import RiskLevel

from ....domain.entities.base_node import BaseNode
from ....domain.entities.node_definition import NodeDefinition
from ....domain.entities.node_metadata import NodeMetadata
from ....domain.catalog._catalog_ns import _CATALOG_NS

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
        raise NotImplementedError(
            "이메일 발송은 REQ-005 toolset.EmailSendTool을 통해 처리. "
            "execution_engine.ToolsetExecutor가 node_type 기반으로 toolset.execute_tool() 호출. "
            "BaseNode.process() 직접 호출 X."
        )


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
