from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import uuid5

from common_schemas.enums import RiskLevel

from ....domain.entities.base_node import BaseNode
from ....domain.entities.node_definition import NodeDefinition
from ....domain.entities.node_metadata import NodeMetadata
from .._catalog_ns import _CATALOG_NS

_NODE_TYPE = "api_poll_trigger"
_NODE_ID = uuid5(_CATALOG_NS, _NODE_TYPE)


@dataclass
class ApiPollTriggerInput:
    response: dict[str, Any]
    previous_response: dict[str, Any] | None = None
    changed: bool = False


@dataclass
class ApiPollTriggerOutput:
    response: dict[str, Any]
    previous_response: dict[str, Any] | None
    changed: bool
    diff_keys: list[str]


class ApiPollTriggerNode(BaseNode[ApiPollTriggerInput, ApiPollTriggerOutput]):
    metadata = NodeMetadata(
        node_id=_NODE_ID,
        name="API 폴링 트리거",
        category="트리거",
        risk_level=RiskLevel.LOW,
        is_mvp=True,
    )
    input_schema = ApiPollTriggerInput
    output_schema = ApiPollTriggerOutput

    async def process(self, input: ApiPollTriggerInput) -> ApiPollTriggerOutput:
        diff_keys: list[str] = []
        if input.previous_response is not None:
            for key in input.response:
                if input.response.get(key) != input.previous_response.get(key):
                    diff_keys.append(key)
        return ApiPollTriggerOutput(
            response=input.response,
            previous_response=input.previous_response,
            changed=input.changed or bool(diff_keys),
            diff_keys=diff_keys,
        )


def get_node_definition() -> NodeDefinition:
    return NodeDefinition(
        node_id=_NODE_ID,
        node_type=_NODE_TYPE,
        name="API 폴링 트리거",
        category="트리거",
        version="1.0.0",
        input_schema={
            "type": "object",
            "properties": {
                "response": {"type": "object"},
                "previous_response": {"type": "object"},
                "changed": {"type": "boolean", "default": False},
            },
            "required": ["response"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "response": {"type": "object"},
                "previous_response": {"type": "object"},
                "changed": {"type": "boolean"},
                "diff_keys": {"type": "array", "items": {"type": "string"}},
            },
        },
        parameter_schema={},
        risk_level=RiskLevel.LOW,
        required_connections=[],
        description="외부 API를 주기적으로 폴링하여 응답 변경 감지 시 워크플로우 시작",
        is_mvp=True,
        service_type=None,
    )
