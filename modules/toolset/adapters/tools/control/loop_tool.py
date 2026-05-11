from __future__ import annotations

from typing import Any

from common_schemas.enums import RiskLevel

from ....domain.base_tool import BaseTool
from ....domain.exceptions import ToolExecutionError

_DEFAULT_MAX = 100


class LoopTool(BaseTool):
    name = "loop"
    description = "배열 순회 — 각 항목에 인덱스를 붙여 반환"
    version = "1.0.0"
    risk_level = RiskLevel.MEDIUM

    input_schema = {
        "type": "object",
        "properties": {
            "items": {"type": "array"},
            "max_iterations": {"type": "integer", "minimum": 1, "maximum": 1000, "default": _DEFAULT_MAX},
        },
        "required": ["items"],
    }

    output_schema = {
        "type": "object",
        "properties": {
            "results": {"type": "array"},
            "count": {"type": "integer"},
        },
        "required": ["results", "count"],
    }

    async def execute(self, input_data: dict[str, Any], **kwargs) -> dict[str, Any]:
        items = input_data["items"]
        max_iter = input_data.get("max_iterations", _DEFAULT_MAX)

        if not isinstance(items, list):
            raise ToolExecutionError(message="'items' must be a JSON array", code="TOOL_EXECUTION_ERROR")

        results = [{"index": i, "item": item} for i, item in enumerate(items[:max_iter])]
        return {"results": results, "count": len(results)}
