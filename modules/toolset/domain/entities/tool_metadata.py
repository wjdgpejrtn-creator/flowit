from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from common_schemas.enums import RiskLevel

if TYPE_CHECKING:
    from .base_tool import BaseTool


@dataclass(frozen=True)
class ToolMetadata:
    tool_id: str
    name: str
    description: str
    risk_level: RiskLevel
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    is_enabled: bool = True

    @classmethod
    def from_tool(cls, tool: BaseTool) -> ToolMetadata:
        return cls(
            tool_id=tool.tool_id,
            name=tool.name,
            description=tool.description,
            risk_level=tool.risk_level,
            input_schema=tool.input_schema,
            output_schema=tool.output_schema,
        )
