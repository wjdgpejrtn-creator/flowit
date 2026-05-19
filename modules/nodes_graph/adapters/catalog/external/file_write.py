from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid5

from common_schemas.enums import RiskLevel

from ....domain.entities.base_node import BaseNode
from ....domain.entities.node_definition import NodeDefinition
from ....domain.entities.node_metadata import NodeMetadata
from ....domain.catalog._catalog_ns import _CATALOG_NS

_NODE_TYPE = "file_write"
_NODE_ID = uuid5(_CATALOG_NS, _NODE_TYPE)


@dataclass
class FileWriteInput:
    path: str
    content: str
    encoding: str = "utf-8"
    mode: str = "w"                                             # w | a
    create_parents: bool = False


@dataclass
class FileWriteOutput:
    path: str
    bytes_written: int
    success: bool


class FileWriteNode(BaseNode[FileWriteInput, FileWriteOutput]):
    metadata = NodeMetadata(
        node_id=_NODE_ID,
        name="파일 쓰기",
        category="utility",
        risk_level=RiskLevel.MEDIUM,
        is_mvp=True,
    )
    input_schema = FileWriteInput
    output_schema = FileWriteOutput

    async def process(self, input: FileWriteInput) -> FileWriteOutput:
        raise NotImplementedError(
            "파일 쓰기는 REQ-005 toolset.FileWriteTool을 통해 처리. "
            "execution_engine.ToolsetExecutor가 node_type 기반으로 toolset.execute_tool() 호출. "
            "BaseNode.process() 직접 호출 X."
        )


def get_node_definition() -> NodeDefinition:
    return NodeDefinition(
        node_id=_NODE_ID,
        node_type=_NODE_TYPE,
        name="파일 쓰기",
        category="utility",
        version="1.0.0",
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
                "encoding": {"type": "string", "default": "utf-8"},
                "mode": {"type": "string", "enum": ["w", "a"], "default": "w"},
                "create_parents": {"type": "boolean", "default": False},
            },
            "required": ["path", "content"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "bytes_written": {"type": "integer"},
                "success": {"type": "boolean"},
            },
            "required": ["path", "bytes_written", "success"],
        },
        parameter_schema={},
        risk_level=RiskLevel.MEDIUM,
        required_connections=[],
        description="파일 쓰기/추가. mode=a 시 기존 파일에 append. create_parents=true 시 중간 디렉토리 생성",
        is_mvp=True,
        service_type=None,
    )
