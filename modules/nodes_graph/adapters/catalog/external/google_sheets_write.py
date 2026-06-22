from __future__ import annotations

from dataclasses import dataclass, field
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

_NODE_TYPE = "google_sheets_write"
_NODE_ID = uuid5(_CATALOG_NS, _NODE_TYPE)
_TIMEOUT_SECONDS = 60


@dataclass
class GoogleSheetsWriteInput:
    spreadsheet_id: str
    range_a1: str                                                       # e.g. "Sheet1!A1"
    values: list[list[Any]] = field(default_factory=list)               # 2D 행렬 (행 우선)
    mode: str = "update"                                                # update(덮어쓰기) | append(추가)
    value_input_option: str = "USER_ENTERED"                            # USER_ENTERED | RAW


@dataclass
class GoogleSheetsWriteOutput:
    updated_range: str                                                  # 실제 갱신된 범위
    updated_rows: int
    updated_columns: int
    updated_cells: int


class GoogleSheetsWriteNode(BaseNode[GoogleSheetsWriteInput, GoogleSheetsWriteOutput]):
    metadata = NodeMetadata(
        node_id=_NODE_ID,
        name="Google Sheets 쓰기",
        category="integration",
        risk_level=RiskLevel.HIGH,
        is_mvp=True,
    )
    input_schema = GoogleSheetsWriteInput
    output_schema = GoogleSheetsWriteOutput

    async def process(self, input: GoogleSheetsWriteInput, context: NodeContext) -> GoogleSheetsWriteOutput:
        # connection_token = Google OAuth access token. spreadsheets.values.update / .append.
        if not context.connection_token:
            raise ValidationError("google_sheets_write는 credential(Google OAuth 토큰)이 필요하다")
        if input.mode not in ("update", "append"):
            raise ValidationError(f"mode는 update/append만 허용: {input.mode!r}")

        # 사용자가 시트 URL 전체/꼬리를 붙여넣어도 순수 ID로 정규화(read 노드와 동일).
        spreadsheet_id = extract_spreadsheet_id(input.spreadsheet_id)
        base = (
            f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}"
            f"/values/{quote(input.range_a1, safe='')}"
        )
        headers = {
            "Authorization": f"Bearer {context.connection_token}",
            "Content-Type": "application/json",
        }
        body = {"values": input.values}
        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            if input.mode == "append":
                response = await client.post(
                    f"{base}:append",
                    params={"valueInputOption": input.value_input_option, "insertDataOption": "INSERT_ROWS"},
                    json=body,
                    headers=headers,
                )
            else:
                response = await client.put(
                    base,
                    params={"valueInputOption": input.value_input_option},
                    json=body,
                    headers=headers,
                )

        if response.status_code >= 400:
            raise ExecutionError(friendly_sheets_error(response.status_code, response.text))

        data = response.json()
        # append는 updates 하위에, update는 최상위에 갱신 통계를 둔다.
        updates = data.get("updates", data)
        return GoogleSheetsWriteOutput(
            updated_range=updates.get("updatedRange", input.range_a1),
            updated_rows=int(updates.get("updatedRows", 0) or 0),
            updated_columns=int(updates.get("updatedColumns", 0) or 0),
            updated_cells=int(updates.get("updatedCells", 0) or 0),
        )


def get_node_definition() -> NodeDefinition:
    return NodeDefinition(
        node_id=_NODE_ID,
        node_type=_NODE_TYPE,
        name="Google Sheets 쓰기",
        category="integration",
        version="1.0.0",
        input_schema={
            "type": "object",
            "properties": {
                "spreadsheet_id": {
                    "type": "string",
                    "description": "스프레드시트 ID. 전체 URL을 붙여넣어도 ID만 자동 추출됨",
                },
                "range_a1": {"type": "string", "description": "A1 표기법 (Sheet1!A1)"},
                "values": {"type": "array", "items": {"type": "array"}, "description": "2D 행렬(행 우선)"},
                "mode": {"type": "string", "enum": ["update", "append"], "default": "update"},
                "value_input_option": {
                    "type": "string",
                    "enum": ["USER_ENTERED", "RAW"],
                    "default": "USER_ENTERED",
                },
            },
            "required": ["spreadsheet_id", "range_a1", "values"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "updated_range": {"type": "string"},
                "updated_rows": {"type": "integer"},
                "updated_columns": {"type": "integer"},
                "updated_cells": {"type": "integer"},
            },
        },
        parameter_schema={},
        risk_level=RiskLevel.HIGH,
        required_connections=["google"],
        description="Google Sheets 지정 범위에 값 쓰기/추가 (values.update·append). Google OAuth 자격증명 필요",
        is_mvp=True,
        service_type="google_workspace",
    )
