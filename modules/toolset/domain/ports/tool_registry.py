from __future__ import annotations

from abc import ABC, abstractmethod

from ..entities.base_tool import BaseTool
from ..entities.tool_metadata import ToolMetadata


class ToolRegistry(ABC):
    """도구 등록 및 조회 Port. 구현체: adapters/tool_registry_adapter.py"""

    @abstractmethod
    def get_tool(self, tool_id: str) -> BaseTool:
        """Raises: NotFoundError — tool_id 미등록"""
        ...

    @abstractmethod
    def list_tools(self) -> list[BaseTool]:
        ...

    @abstractmethod
    def list_metadata(self, category: str | None = None) -> list[ToolMetadata]:
        ...

    @abstractmethod
    def register_tool(self, tool: BaseTool) -> None:
        ...

    def is_registered(self, tool_id: str) -> bool:
        try:
            self.get_tool(tool_id)
            return True
        except Exception:
            return False
