from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from typing import Any
from uuid import uuid5

from common_schemas.enums import RiskLevel

from ....domain.entities.base_node import BaseNode
from ....domain.entities.node_definition import NodeDefinition
from ....domain.entities.node_metadata import NodeMetadata
from .._catalog_ns import _CATALOG_NS

_NODE_TYPE = "csv_build"
_NODE_ID = uuid5(_CATALOG_NS, _NODE_TYPE)


@dataclass
class CsvBuildInput:
    rows: list[dict[str, Any]]
    delimiter: str = ","


@dataclass
class CsvBuildOutput:
    csv_string: str
    row_count: int


class CsvBuildNode(BaseNode[CsvBuildInput, CsvBuildOutput]):
    metadata = NodeMetadata(
        node_id=_NODE_ID,
        name="CSV 생성",
        category="데이터 처리",
        risk_level=RiskLevel.LOW,
        is_mvp=True,
    )
    input_schema = CsvBuildInput
    output_schema = CsvBuildOutput

    async def process(self, input: CsvBuildInput) -> CsvBuildOutput:
        if not input.rows:
            return CsvBuildOutput(csv_string="", row_count=0)
        buf = io.StringIO()
        headers = list(input.rows[0].keys())
        writer = csv.DictWriter(buf, fieldnames=headers, delimiter=input.delimiter)
        writer.writeheader()
        writer.writerows(input.rows)
        return CsvBuildOutput(csv_string=buf.getvalue(), row_count=len(input.rows))


def get_node_definition() -> NodeDefinition:
    return NodeDefinition(
        node_id=_NODE_ID,
        node_type=_NODE_TYPE,
        name="CSV 생성",
        category="데이터 처리",
        version="1.0.0",
        input_schema={
            "type": "object",
            "properties": {
                "rows": {"type": "array", "items": {"type": "object"}},
                "delimiter": {"type": "string", "default": ","},
            },
            "required": ["rows"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "csv_string": {"type": "string"},
                "row_count": {"type": "integer"},
            },
        },
        parameter_schema={},
        risk_level=RiskLevel.LOW,
        required_connections=[],
        description="행 데이터 목록을 CSV 문자열로 변환",
        is_mvp=True,
        service_type=None,
    )
