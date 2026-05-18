from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any
from uuid import UUID

from common_schemas.enums import RiskLevel

if TYPE_CHECKING:
    from ..base_tool import BaseTool


class ToolCategory(str, Enum):
    """Tool 카테고리 — 내부 AI 도구 분류용 (Node 카탈로그와 무관)."""
    API = "api"
    FILE = "file"
    TRANSFORM = "transform"
    CONTROL = "control"
    NOTIFICATION = "notification"


@dataclass(frozen=True)
class ToolMetadata:
    """Tool 카탈로그 메타데이터.

    tool_id: 내부 추적(internal tracking) 전용 UUID. 외부 식별자는 name을 사용한다.
    """
    tool_id: UUID
    name: str
    version: str
    category: ToolCategory
    description: str
    risk_level: RiskLevel
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    capabilities: list[str] = field(default_factory=list)
    is_enabled: bool = True

    @classmethod
    def from_tool(cls, tool: BaseTool, tool_id: UUID, category: ToolCategory) -> ToolMetadata:
        return cls(
            tool_id=tool_id,
            name=tool.name,
            version=tool.version,
            category=category,
            description=tool.description,
            risk_level=tool.risk_level,
            input_schema=tool.input_schema,
            output_schema=tool.output_schema,
            capabilities=tool.capabilities,
        )
