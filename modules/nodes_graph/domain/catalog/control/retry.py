from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import uuid5

from common_schemas.enums import RiskLevel

from ....domain.entities.base_node import BaseNode
from ....domain.entities.node_definition import NodeDefinition
from ....domain.entities.node_metadata import NodeMetadata
from .._catalog_ns import _CATALOG_NS

_NODE_TYPE = "retry"
_NODE_ID = uuid5(_CATALOG_NS, _NODE_TYPE)


@dataclass
class RetryInput:
    max_attempts: int = 3
    delay_seconds: float = 1.0
    backoff_multiplier: float = 2.0
    value: Any = None   # 하위 노드로 전달할 pass-through 값


@dataclass
class RetryOutput:
    value: Any
    config: dict[str, Any]   # 실행 엔진이 읽는 재시도 설정


class RetryNode(BaseNode[RetryInput, RetryOutput]):
    metadata = NodeMetadata(
        node_id=_NODE_ID,
        name="재시도",
        category="조건/제어",
        risk_level=RiskLevel.LOW,
        is_mvp=True,
    )
    input_schema = RetryInput
    output_schema = RetryOutput

    async def process(self, input: RetryInput) -> RetryOutput:
        return RetryOutput(
            value=input.value,
            config={
                "max_attempts": input.max_attempts,
                "delay_seconds": input.delay_seconds,
                "backoff_multiplier": input.backoff_multiplier,
            },
        )


def get_node_definition() -> NodeDefinition:
    return NodeDefinition(
        node_id=_NODE_ID,
        node_type=_NODE_TYPE,
        name="재시도",
        category="조건/제어",
        version="1.0.0",
        input_schema={
            "type": "object",
            "properties": {
                "max_attempts": {"type": "integer", "default": 3},
                "delay_seconds": {"type": "number", "default": 1.0},
                "backoff_multiplier": {"type": "number", "default": 2.0},
                "value": {},
            },
        },
        output_schema={
            "type": "object",
            "properties": {
                "value": {},
                "config": {"type": "object"},
            },
        },
        parameter_schema={},
        risk_level=RiskLevel.LOW,
        required_connections=[],
        description="하위 노드 실패 시 지수 백오프로 재시도 (실행 엔진 처리)",
        is_mvp=True,
        service_type=None,
    )
