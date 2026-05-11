from __future__ import annotations

import asyncio
from typing import Any

from common_schemas.enums import RiskLevel

from ....domain.base_tool import BaseTool
from ....domain.exceptions import ToolExecutionError

_MAX_DELAY = 300


class DelayTool(BaseTool):
    name = "delay"
    description = "대기/지연 (asyncio.sleep)"
    version = "1.0.0"
    risk_level = RiskLevel.LOW

    input_schema = {
        "type": "object",
        "properties": {
            "seconds": {"type": "number", "minimum": 0, "maximum": _MAX_DELAY},
        },
        "required": ["seconds"],
    }

    output_schema = {
        "type": "object",
        "properties": {
            "delayed_seconds": {"type": "number"},
            "completed": {"type": "boolean"},
        },
        "required": ["delayed_seconds", "completed"],
    }

    async def execute(self, input_data: dict[str, Any], **kwargs) -> dict[str, Any]:
        seconds = input_data["seconds"]

        if seconds > _MAX_DELAY:
            raise ToolExecutionError(
                message=f"Delay exceeds maximum allowed ({_MAX_DELAY}s)",
                code="TOOL_EXECUTION_ERROR",
            )

        await asyncio.sleep(seconds)
        return {"delayed_seconds": seconds, "completed": True}
