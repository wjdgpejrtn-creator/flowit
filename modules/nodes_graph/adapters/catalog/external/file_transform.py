from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from io import StringIO
from uuid import uuid5

from common_schemas import NodeContext
from common_schemas.enums import RiskLevel
from common_schemas.exceptions import ValidationError

from ....domain.catalog._catalog_ns import _CATALOG_NS
from ....domain.entities.base_node import BaseNode
from ....domain.entities.node_definition import NodeDefinition
from ....domain.entities.node_metadata import NodeMetadata
from ._file_sandbox import resolve_sandboxed_path

_NODE_TYPE = "file_transform"
_NODE_ID = uuid5(_CATALOG_NS, _NODE_TYPE)
_SUPPORTED_FORMATS = {"csv", "json"}


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

    async def process(self, input: FileTransformInput, context: NodeContext) -> FileTransformOutput:
        if input.source_format not in _SUPPORTED_FORMATS or input.target_format not in _SUPPORTED_FORMATS:
            raise ValidationError("source/target_format은 'csv' 또는 'json'만 허용")

        src = resolve_sandboxed_path(input.source_path)
        dst = resolve_sandboxed_path(input.target_path)
        if not src.is_file():
            raise ValidationError(f"원본 파일을 찾을 수 없음: {input.source_path!r}")

        raw = src.read_text(encoding=input.encoding)
        if input.source_format == "csv":
            rows = list(csv.DictReader(StringIO(raw)))
        else:
            loaded = json.loads(raw)
            rows = loaded if isinstance(loaded, list) else [loaded]

        if input.target_format == "json":
            dst.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding=input.encoding)
        elif not rows:
            dst.write_text("", encoding=input.encoding)
        else:
            buf = StringIO()
            writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
            dst.write_text(buf.getvalue(), encoding=input.encoding)

        return FileTransformOutput(target_path=str(dst), rows_processed=len(rows))


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
