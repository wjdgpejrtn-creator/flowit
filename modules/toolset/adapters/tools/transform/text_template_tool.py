from __future__ import annotations

from string import Formatter
from typing import Any

from common_schemas.enums import RiskLevel

from ....domain.base_tool import BaseTool
from ....domain.exceptions import ToolExecutionError


class TextTemplateTool(BaseTool):
    name = "text_template"
    description = "Jinja2 스타일 변수 치환 템플릿 렌더링 ({variable} 문법)"
    version = "1.0.0"
    risk_level = RiskLevel.LOW

    input_schema = {
        "type": "object",
        "properties": {
            "template": {"type": "string"},
            "variables": {"type": "object"},
        },
        "required": ["template", "variables"],
    }

    output_schema = {
        "type": "object",
        "properties": {
            "rendered": {"type": "string"},
        },
        "required": ["rendered"],
    }

    async def execute(self, input_data: dict[str, Any], **kwargs) -> dict[str, Any]:
        template = input_data["template"]
        variables = input_data.get("variables") or {}

        required_keys = {field_name for _, field_name, _, _ in Formatter().parse(template) if field_name is not None}
        missing = required_keys - variables.keys()
        if missing:
            raise ToolExecutionError(
                message=f"Template variables missing: {sorted(missing)}",
                code="TOOL_EXECUTION_ERROR",
            )

        try:
            rendered = template.format_map(variables)
        except (KeyError, ValueError, IndexError) as e:
            raise ToolExecutionError(message=f"Template rendering failed: {e}", code="TOOL_EXECUTION_ERROR") from e

        return {"rendered": rendered}
