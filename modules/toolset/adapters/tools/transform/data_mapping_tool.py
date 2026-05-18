from __future__ import annotations

from typing import Any

from common_schemas.enums import RiskLevel

from ....domain.base_tool import BaseTool
from ....domain.entities.tool_metadata import ToolCategory
from ....domain.exceptions import ToolExecutionError


class DataMappingTool(BaseTool):
    name = "data_mapping"
    description = "필드 매핑/리네이밍 (old_field → new_field)"
    version = "1.0.0"
    risk_level = RiskLevel.LOW
    category = ToolCategory.TRANSFORM
    capabilities = ["data_mapping", "field_mapping", "data_processing"]

    input_schema = {
        "type": "object",
        "properties": {
            "data": {"type": "object"},
            "mapping": {
                "type": "object",
                "description": "{'원본_필드': '새_필드'} 형태의 매핑 테이블",
            },
            "drop_unmapped": {"type": "boolean", "default": False},
        },
        "required": ["data", "mapping"],
    }

    output_schema = {
        "type": "object",
        "properties": {
            "result": {"type": "object"},
            "mapped_count": {"type": "integer"},
        },
        "required": ["result", "mapped_count"],
    }

    async def execute(self, input_data: dict[str, Any], **kwargs) -> dict[str, Any]:
        data: dict = input_data["data"]
        mapping: dict = input_data["mapping"]
        drop_unmapped: bool = input_data.get("drop_unmapped", False)

        if not isinstance(data, dict):
            raise ToolExecutionError(message="'data' must be a JSON object", code="TOOL_EXECUTION_ERROR")

        result: dict[str, Any] = {}
        mapped_count = 0

        for key, value in data.items():
            if key in mapping:
                result[mapping[key]] = value
                mapped_count += 1
            elif not drop_unmapped:
                result[key] = value

        return {"result": result, "mapped_count": mapped_count}
