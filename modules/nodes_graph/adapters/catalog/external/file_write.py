from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid5

from common_schemas import NodeContext
from common_schemas.enums import RiskLevel
from common_schemas.exceptions import ValidationError

from ....domain.catalog._catalog_ns import _CATALOG_NS
from ....domain.entities.base_node import BaseNode
from ....domain.entities.node_definition import NodeDefinition
from ....domain.entities.node_metadata import NodeMetadata
from ._file_sandbox import resolve_sandboxed_path

_NODE_TYPE = "file_write"
_NODE_ID = uuid5(_CATALOG_NS, _NODE_TYPE)


@dataclass
class FileWriteInput:
    path: str
    content: str
    encoding: str = "utf-8"
    mode: str = "w"  # w | a
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

    async def process(self, input: FileWriteInput, context: NodeContext) -> FileWriteOutput:
        file_path = resolve_sandboxed_path(input.path)
        if file_path.is_dir():
            raise ValidationError(f"경로가 디렉토리임: {input.path!r}")
        if input.mode not in ("w", "a"):
            raise ValidationError(f"mode는 'w' 또는 'a'만 허용: {input.mode!r}")

        if input.create_parents:
            file_path.parent.mkdir(parents=True, exist_ok=True)
        with file_path.open(mode=input.mode, encoding=input.encoding) as f:
            f.write(input.content)
        return FileWriteOutput(
            path=str(file_path),
            bytes_written=len(input.content.encode(input.encoding)),
            success=True,
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
                "path": {"type": "string", "description": "쓸 파일 경로"},
                "content": {"type": "string", "description": "파일에 쓸 내용"},
                "encoding": {"type": "string", "default": "utf-8", "description": "텍스트 인코딩. 기본값 utf-8"},
                "mode": {
                    "type": "string",
                    "enum": ["w", "a"],
                    "default": "w",
                    "description": "w=덮어쓰기, a=기존 파일에 추가. 기본값 w",
                },
                "create_parents": {
                    "type": "boolean",
                    "default": False,
                    "description": "true면 상위 디렉터리를 자동 생성. 기본값 false",
                },
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
