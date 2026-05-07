from __future__ import annotations

from abc import ABC, abstractmethod

from ..entities.base_tool import BaseTool
from ..entities.tool_metadata import ToolMetadata


class ToolRegistry(ABC):
    """도구 등록 및 조회 Port. 구현체: adapters/tool_registry_adapter.py"""

    @abstractmethod
    def get(self, tool_name: str) -> BaseTool:
        """Raises: NotFoundError — tool_name 미등록"""
        ...

    @abstractmethod
    def list_all(self) -> list[ToolMetadata]:
        ...

    @abstractmethod
    def list_by_category(self, category: str) -> list[ToolMetadata]:
        ...

