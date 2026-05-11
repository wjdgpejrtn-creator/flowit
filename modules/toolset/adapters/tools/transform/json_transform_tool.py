from __future__ import annotations

import re
from typing import Any

from common_schemas.enums import RiskLevel

from ....domain.base_tool import BaseTool
from ....domain.exceptions import ToolExecutionError

_SENTINEL = object()


def _resolve_path(data: Any, expression: str) -> Any:
    """점 표기법 + 배열 인덱스 지원 (예: "a.b[0].c")."""
    tokens = re.split(r"\.(?![^\[]*\])", expression)
    current = data
    for token in tokens:
        if current is _SENTINEL:
            break
        m = re.fullmatch(r"(\w+)\[(\d+)\]", token)
        if m:
            key, idx = m.group(1), int(m.group(2))
            current = current.get(key, _SENTINEL) if isinstance(current, dict) else _SENTINEL
            if current is not _SENTINEL:
                current = current[idx] if isinstance(current, list) and idx < len(current) else _SENTINEL
        elif isinstance(current, dict):
            current = current.get(token, _SENTINEL)
        else:
            current = _SENTINEL
    return current


class JsonTransformTool(BaseTool):
    name = "json_transform"
    description = "점 표기법 경로로 JSON 데이터 추출/변환"
    version = "1.0.0"
    risk_level = RiskLevel.LOW

    input_schema = {
        "type": "object",
        "properties": {
            "data": {},
            "expression": {"type": "string"},
        },
        "required": ["data", "expression"],
    }

    output_schema = {
        "type": "object",
        "properties": {
            "result": {},
            "matched": {"type": "boolean"},
        },
        "required": ["result", "matched"],
    }

    async def execute(self, input_data: dict[str, Any], **kwargs) -> dict[str, Any]:
        data = input_data["data"]
        expression = input_data["expression"]

        if not expression.strip():
            raise ToolExecutionError(message="expression must not be empty", code="TOOL_EXECUTION_ERROR")

        result = _resolve_path(data, expression)
        matched = result is not _SENTINEL
        return {"result": result if matched else None, "matched": matched}
