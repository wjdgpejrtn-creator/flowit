from __future__ import annotations

from common_schemas.enums import RiskLevel

from ...domain.entities.tool_metadata import ToolMetadata
from ...domain.ports.tool_registry import ToolRegistry


class ListToolsUseCase:
    def __init__(self, tool_registry: ToolRegistry) -> None:
        self._registry = tool_registry

    def execute(
        self,
        category: str | None = None,
        risk_level: RiskLevel | None = None,
    ) -> list[ToolMetadata]:
        if category is not None:
            metadata_list = self._registry.list_by_category(category)
        else:
            metadata_list = self._registry.list_all()

        if risk_level is not None:
            metadata_list = [m for m in metadata_list if m.risk_level == risk_level]

        return [m for m in metadata_list if m.is_enabled]
