from __future__ import annotations

from typing import Any

import jmespath
import jmespath.exceptions

from common_schemas.enums import RiskLevel

from ....domain.base_tool import BaseTool
from ....domain.exceptions import ToolExecutionError


class JsonTransformTool(BaseTool):
    name = "json_transform"
    description = "JMESPath 표현식으로 JSON 데이터 추출/변환"
    version = "1.0.0"
    risk_level = RiskLevel.LOW

    input_schema = {
        "type": "object",
        "properties": {
            "data": {},
            "expression": {"type": "string", "description": "JMESPath 표현식 (예: 'a.b', 'items[0].id', 'items[*].name')"},
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

        try:
            result = jmespath.search(expression, data)
        except jmespath.exceptions.JMESPathError as e:
            raise ToolExecutionError(
                message=f"Invalid JMESPath expression '{expression}': {e}",
                code="TOOL_EXECUTION_ERROR",
            ) from e

        return {"result": result, "matched": result is not None}
