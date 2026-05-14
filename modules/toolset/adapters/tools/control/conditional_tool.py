from __future__ import annotations

from typing import Any

from common_schemas.enums import RiskLevel

from ....domain.base_tool import BaseTool
from ....domain.exceptions import ToolExecutionError

_OPS = {
    "eq": lambda a, b: a == b,
    "ne": lambda a, b: a != b,
    "gt": lambda a, b: a > b,
    "lt": lambda a, b: a < b,
    "gte": lambda a, b: a >= b,
    "lte": lambda a, b: a <= b,
    "contains": lambda a, b: b in a,
    "startswith": lambda a, b: str(a).startswith(str(b)),
    "endswith": lambda a, b: str(a).endswith(str(b)),
    "in": lambda a, b: a in b,
}


class ConditionalTool(BaseTool):
    name = "conditional"
    description = "조건 분기 (if/else 로직)"
    version = "1.0.0"
    risk_level = RiskLevel.LOW

    input_schema = {
        "type": "object",
        "properties": {
            "left": {},
            "operator": {
                "type": "string",
                "enum": list(_OPS.keys()),
            },
            "right": {},
        },
        "required": ["left", "operator", "right"],
    }

    output_schema = {
        "type": "object",
        "properties": {
            "result": {"type": "boolean"},
            "branch": {"type": "string", "enum": ["true_branch", "false_branch"]},
        },
        "required": ["result", "branch"],
    }

    async def execute(self, input_data: dict[str, Any], **kwargs) -> dict[str, Any]:
        left = input_data["left"]
        operator = input_data["operator"]
        right = input_data["right"]

        op_fn = _OPS.get(operator)
        if op_fn is None:
            raise ToolExecutionError(
                message=f"Unknown operator '{operator}'. Supported: {list(_OPS.keys())}",
                code="TOOL_EXECUTION_ERROR",
            )

        try:
            result = bool(op_fn(left, right))
        except TypeError as e:
            raise ToolExecutionError(
                message=f"Operator '{operator}' cannot compare {type(left).__name__} and {type(right).__name__}: {e}",
                code="TOOL_EXECUTION_ERROR",
            ) from e

        return {"result": result, "branch": "true_branch" if result else "false_branch"}
