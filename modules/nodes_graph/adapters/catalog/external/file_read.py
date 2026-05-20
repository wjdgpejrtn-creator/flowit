from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import uuid5

from common_schemas import NodeContext
from common_schemas.enums import RiskLevel

from ....domain.entities.base_node import BaseNode
from ....domain.entities.node_definition import NodeDefinition
from ....domain.entities.node_metadata import NodeMetadata
from ....domain.catalog._catalog_ns import _CATALOG_NS

_NODE_TYPE = "file_read"
_NODE_ID = uuid5(_CATALOG_NS, _NODE_TYPE)


@dataclass
class FileReadInput:
    path: str
    encoding: str = "utf-8"
    binary: bool = False


@dataclass
class FileReadOutput:
    content: Any                                                # str(text) | str(hex when binary=True)
    size_bytes: int
    path: str


class FileReadNode(BaseNode[FileReadInput, FileReadOutput]):
    metadata = NodeMetadata(
        node_id=_NODE_ID,
        name="파일 읽기",
        category="utility",
        risk_level=RiskLevel.LOW,
        is_mvp=True,
    )
    input_schema = FileReadInput
    output_schema = FileReadOutput

    async def process(self, input: FileReadInput, context: NodeContext) -> FileReadOutput:
        raise NotImplementedError(
            "파일 읽기는 REQ-005 toolset.FileReadTool을 통해 처리. "
            "execution_engine.ToolsetExecutor가 node_type 기반으로 toolset.execute_tool() 호출. "
            "BaseNode.process() 직접 호출 X."
        )


def get_node_definition() -> NodeDefinition:
    return NodeDefinition(
        node_id=_NODE_ID,
        node_type=_NODE_TYPE,
        name="파일 읽기",
        category="utility",
        version="1.0.0",
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "encoding": {"type": "string", "default": "utf-8"},
                "binary": {"type": "boolean", "default": False},
            },
            "required": ["path"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "content": {},
                "size_bytes": {"type": "integer"},
                "path": {"type": "string"},
            },
            "required": ["content", "size_bytes", "path"],
        },
        parameter_schema={},
        risk_level=RiskLevel.LOW,
        required_connections=[],
        description="파일 텍스트/바이너리 읽기. binary=true 시 hex 문자열 반환",
        is_mvp=True,
        service_type=None,
    )
