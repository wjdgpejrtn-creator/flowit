from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid5

from common_schemas.enums import RiskLevel

from ....domain.entities.base_node import BaseNode
from ....domain.entities.node_definition import NodeDefinition
from ....domain.entities.node_metadata import NodeMetadata
from .._catalog_ns import _CATALOG_NS

_NODE_TYPE = "file_watch_trigger"
_NODE_ID = uuid5(_CATALOG_NS, _NODE_TYPE)


@dataclass
class FileWatchTriggerInput:
    file_path: str
    event_type: str              # created | modified | deleted | moved
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class FileWatchTriggerOutput:
    file_path: str
    event_type: str
    payload: dict[str, Any]


class FileWatchTriggerNode(BaseNode[FileWatchTriggerInput, FileWatchTriggerOutput]):
    metadata = NodeMetadata(
        node_id=_NODE_ID,
        name="파일 감시 트리거",
        category="trigger",
        risk_level=RiskLevel.LOW,
        is_mvp=True,
    )
    input_schema = FileWatchTriggerInput
    output_schema = FileWatchTriggerOutput

    async def process(self, input: FileWatchTriggerInput) -> FileWatchTriggerOutput:
        return FileWatchTriggerOutput(
            file_path=input.file_path,
            event_type=input.event_type,
            payload=input.payload,
        )


def get_node_definition() -> NodeDefinition:
    return NodeDefinition(
        node_id=_NODE_ID,
        node_type=_NODE_TYPE,
        name="파일 감시 트리거",
        category="trigger",
        version="1.0.0",
        input_schema={
            "type": "object",
            "properties": {
                "file_path": {"type": "string"},
                "event_type": {"type": "string", "enum": ["created", "modified", "deleted", "moved"]},
                "payload": {"type": "object"},
            },
            "required": ["file_path", "event_type"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "file_path": {"type": "string"},
                "event_type": {"type": "string"},
                "payload": {"type": "object"},
            },
        },
        parameter_schema={},
        risk_level=RiskLevel.LOW,
        required_connections=[],
        description="파일 시스템 변경 감지 트리거. 실행 엔진이 watchdog으로 감시하고 이벤트 주입",
        is_mvp=True,
        service_type=None,
    )
