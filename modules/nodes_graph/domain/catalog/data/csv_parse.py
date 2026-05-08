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

_NODE_TYPE = "csv_parse"
_NODE_ID = uuid5(_CATALOG_NS, _NODE_TYPE)


@dataclass
class CsvParseInput:
    csv_string: str
    delimiter: str = ","
    has_header: bool = True


@dataclass
class CsvParseOutput:
    rows: list[dict[str, Any]]
    headers: list[str]
    row_count: int


class CsvParseNode(BaseNode[CsvParseInput, CsvParseOutput]):
    metadata = NodeMetadata(
        node_id=_NODE_ID,
        name="CSV 파싱",
        category="데이터 처리",
        risk_level=RiskLevel.LOW,
        is_mvp=True,
    )
    input_schema = CsvParseInput
    output_schema = CsvParseOutput

    async def process(self, input: CsvParseInput) -> CsvParseOutput:
        reader = csv.DictReader(io.StringIO(input.csv_string), delimiter=input.delimiter)
        if input.has_header:
            rows = [dict(row) for row in reader]
            headers = list(reader.fieldnames or [])
        else:
            raw = list(csv.reader(io.StringIO(input.csv_string), delimiter=input.delimiter))
            headers = [str(i) for i in range(len(raw[0]))] if raw else []
            rows = [dict(zip(headers, row)) for row in raw]
        return CsvParseOutput(rows=rows, headers=headers, row_count=len(rows))


def get_node_definition() -> NodeDefinition:
    return NodeDefinition(
        node_id=_NODE_ID,
        node_type=_NODE_TYPE,
        name="CSV 파싱",
        category="데이터 처리",
        version="1.0.0",
        input_schema={
            "type": "object",
            "properties": {
                "csv_string": {"type": "string"},
                "delimiter": {"type": "string", "default": ","},
                "has_header": {"type": "boolean", "default": True},
            },
            "required": ["csv_string"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "rows": {"type": "array"},
                "headers": {"type": "array", "items": {"type": "string"}},
                "row_count": {"type": "integer"},
            },
        },
        parameter_schema={},
        risk_level=RiskLevel.LOW,
        required_connections=[],
        description="CSV 문자열을 파싱하여 행/열 데이터 추출",
        is_mvp=True,
        service_type=None,
    )
