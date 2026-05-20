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

_NODE_TYPE = "google_sheets_read"
_NODE_ID = uuid5(_CATALOG_NS, _NODE_TYPE)


@dataclass
class GoogleSheetsReadInput:
    spreadsheet_id: str
    range_a1: str                                                       # e.g. "Sheet1!A1:D100"
    value_render_option: str = "FORMATTED_VALUE"                        # FORMATTED_VALUE | UNFORMATTED_VALUE | FORMULA
    date_time_render_option: str = "FORMATTED_STRING"                   # FORMATTED_STRING | SERIAL_NUMBER
    major_dimension: str = "ROWS"                                       # ROWS | COLUMNS


@dataclass
class GoogleSheetsReadOutput:
    range_resolved: str                                                 # 실제 반환된 범위
    major_dimension: str
    values: list[list[Any]]
    row_count: int


class GoogleSheetsReadNode(BaseNode[GoogleSheetsReadInput, GoogleSheetsReadOutput]):
    metadata = NodeMetadata(
        node_id=_NODE_ID,
        name="Google Sheets 읽기",
        category="integration",
        risk_level=RiskLevel.MEDIUM,
        is_mvp=True,
    )
    input_schema = GoogleSheetsReadInput
    output_schema = GoogleSheetsReadOutput

    async def process(self, input: GoogleSheetsReadInput, context: NodeContext) -> GoogleSheetsReadOutput:
        raise NotImplementedError(
            "외부 서비스 호출은 REQ-005 toolset connector를 통해 처리. "
            "OAuth credential 주입은 REQ-002 CredentialInjectionService 담당."
        )


def get_node_definition() -> NodeDefinition:
    return NodeDefinition(
        node_id=_NODE_ID,
        node_type=_NODE_TYPE,
        name="Google Sheets 읽기",
        category="integration",
        version="1.0.0",
        input_schema={
            "type": "object",
            "properties": {
                "spreadsheet_id": {"type": "string"},
                "range_a1": {"type": "string", "description": "A1 표기법 (Sheet1!A1:D100)"},
                "value_render_option": {
                    "type": "string",
                    "enum": ["FORMATTED_VALUE", "UNFORMATTED_VALUE", "FORMULA"],
                    "default": "FORMATTED_VALUE",
                },
                "date_time_render_option": {
                    "type": "string",
                    "enum": ["FORMATTED_STRING", "SERIAL_NUMBER"],
                    "default": "FORMATTED_STRING",
                },
                "major_dimension": {
                    "type": "string",
                    "enum": ["ROWS", "COLUMNS"],
                    "default": "ROWS",
                },
            },
            "required": ["spreadsheet_id", "range_a1"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "range_resolved": {"type": "string"},
                "major_dimension": {"type": "string"},
                "values": {"type": "array", "items": {"type": "array"}},
                "row_count": {"type": "integer"},
            },
        },
        parameter_schema={},
        risk_level=RiskLevel.MEDIUM,
        required_connections=["google"],
        description="Google Sheets에서 지정 범위(A1 표기) 값 읽기 (spreadsheets.values.get). Google OAuth 자격증명 필요",
        is_mvp=True,
        service_type="google_workspace",
    )
