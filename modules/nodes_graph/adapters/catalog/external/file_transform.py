from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid5

from common_schemas.enums import RiskLevel

from ....domain.entities.base_node import BaseNode
from ....domain.entities.node_definition import NodeDefinition
from ....domain.entities.node_metadata import NodeMetadata
from ....domain.catalog._catalog_ns import _CATALOG_NS

_NODE_TYPE = "file_transform"
_NODE_ID = uuid5(_CATALOG_NS, _NODE_TYPE)


@dataclass
class FileTransformInput:
    source_path: str
    target_path: str
    source_format: str                                          # csv | json
    target_format: str                                          # csv | json
    encoding: str = "utf-8"


@dataclass
class FileTransformOutput:
    target_path: str
    rows_processed: int


class FileTransformNode(BaseNode[FileTransformInput, FileTransformOutput]):
    metadata = NodeMetadata(
        node_id=_NODE_ID,
        name="파일 형식 변환",
        category="transform",
        risk_level=RiskLevel.LOW,
        is_mvp=True,
    )
    input_schema = FileTransformInput
    output_schema = FileTransformOutput

    async def process(self, input: FileTransformInput) -> FileTransformOutput:
        raise NotImplementedError(
            "파일 형식 변환은 REQ-005 toolset.FileTransformTool을 통해 처리. "
            "execution_engine.ToolsetExecutor가 node_type 기반으로 toolset.execute_tool() 호출. "
            "BaseNode.process() 직접 호출 X."
        )


def get_node_definition() -> NodeDefinition:
    return NodeDefinition(
        node_id=_NODE_ID,
        node_type=_NODE_TYPE,
        name="파일 형식 변환",
        category="transform",
        version="1.0.0",
        input_schema={
            "type": "object",
            "properties": {
                "source_path": {"type": "string"},
                "target_path": {"type": "string"},
                "source_format": {"type": "string", "enum": ["csv", "json"]},
                "target_format": {"type": "string", "enum": ["csv", "json"]},
                "encoding": {"type": "string", "default": "utf-8"},
            },
            "required": ["source_path", "target_path", "source_format", "target_format"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "target_path": {"type": "string"},
                "rows_processed": {"type": "integer"},
            },
            "required": ["target_path", "rows_processed"],
        },
        parameter_schema={},
        risk_level=RiskLevel.LOW,
        required_connections=[],
        description="CSV ↔ JSON 파일 형식 변환",
        is_mvp=True,
        service_type=None,
    )
