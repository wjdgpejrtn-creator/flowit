from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import quote
from uuid import uuid5

import httpx
from common_schemas import NodeContext
from common_schemas.enums import RiskLevel
from common_schemas.exceptions import ExecutionError, ValidationError

from ....domain.catalog._catalog_ns import _CATALOG_NS
from ....domain.entities.base_node import BaseNode
from ....domain.entities.node_definition import NodeDefinition
from ....domain.entities.node_metadata import NodeMetadata
from ._google_sheets_util import extract_spreadsheet_id, friendly_sheets_error

_NODE_TYPE = "google_sheets_read"
_NODE_ID = uuid5(_CATALOG_NS, _NODE_TYPE)
_TIMEOUT_SECONDS = 60


@dataclass
class GoogleSheetsReadInput:
    spreadsheet_id: str
    range_a1: str  # e.g. "Sheet1!A1:D100"
    value_render_option: str = "FORMATTED_VALUE"  # FORMATTED_VALUE | UNFORMATTED_VALUE | FORMULA
    date_time_render_option: str = "FORMATTED_STRING"  # FORMATTED_STRING | SERIAL_NUMBER
    major_dimension: str = "ROWS"  # ROWS | COLUMNS


@dataclass
class GoogleSheetsReadOutput:
    range_resolved: str  # 실제 반환된 범위
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
        # connection_token = Google OAuth access token. spreadsheets.values.get.
        if not context.connection_token:
            raise ValidationError("google_sheets_read는 credential(Google OAuth 토큰)이 필요하다")

        # 사용자가 시트 URL 전체/꼬리를 붙여넣어도 순수 ID로 정규화(붙여넣기 실수 → 404 방지).
        spreadsheet_id = extract_spreadsheet_id(input.spreadsheet_id)
        url = (
            f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}"
            f"/values/{quote(input.range_a1, safe='')}"
        )
        params = {
            "valueRenderOption": input.value_render_option,
            "dateTimeRenderOption": input.date_time_render_option,
            "majorDimension": input.major_dimension,
        }
        headers = {"Authorization": f"Bearer {context.connection_token}"}
        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            response = await client.get(url, params=params, headers=headers)

        if response.status_code >= 400:
            raise ExecutionError(
                friendly_sheets_error(_NODE_TYPE, response.status_code, response.text)
            )

        data = response.json()
        values: list[list[Any]] = data.get("values", [])
        return GoogleSheetsReadOutput(
            range_resolved=data.get("range", input.range_a1),
            major_dimension=data.get("majorDimension", input.major_dimension),
            values=values,
            row_count=len(values),
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
                "spreadsheet_id": {
                    "type": "string",
                    "description": (
                        '스프레드시트 ID(시트 URL의 /d/ 뒤 문자열, 예: "1AbC...xyz"). '
                        "전체 URL을 붙여넣어도 ID만 자동 추출됨. 대상은 네이티브 Google Sheets여야 함"
                        "(업로드된 .xlsx Office 파일은 'Google Sheets로 저장'으로 변환 필요)"
                    ),
                },
                "range_a1": {"type": "string", "description": "A1 표기법 (Sheet1!A1:D100)"},
                "value_render_option": {
                    "type": "string",
                    "enum": ["FORMATTED_VALUE", "UNFORMATTED_VALUE", "FORMULA"],
                    "default": "FORMATTED_VALUE",
                    "description": (
                        "값 표시 방식. FORMATTED_VALUE=서식 적용, "
                        "UNFORMATTED_VALUE=원본값, FORMULA=수식. 기본값 FORMATTED_VALUE"
                    ),
                },
                "date_time_render_option": {
                    "type": "string",
                    "enum": ["FORMATTED_STRING", "SERIAL_NUMBER"],
                    "default": "FORMATTED_STRING",
                    "description": (
                        "날짜·시간 표시 방식. FORMATTED_STRING=문자열, SERIAL_NUMBER=일련번호. 기본값 FORMATTED_STRING"
                    ),
                },
                "major_dimension": {
                    "type": "string",
                    "enum": ["ROWS", "COLUMNS"],
                    "default": "ROWS",
                    "description": "데이터 방향. ROWS=행 기준, COLUMNS=열 기준. 기본값 ROWS",
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
        description="Google Sheets 지정 범위(A1 표기) 값 읽기 (values.get). Google OAuth 자격증명 필요",
        is_mvp=True,
        service_type="google_workspace",
    )
