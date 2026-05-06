from __future__ import annotations

from abc import ABC, abstractmethod

from ..entities.tool_execution_record import ToolExecutionRecord


class ToolExecutionRepository(ABC):
    """
    도구 실행 이력 저장 Port.
    구현체: modules/storage/repositories/ (REQ-001 황대원)
    """

    @abstractmethod
    async def save(self, record: ToolExecutionRecord) -> None:
        ...

    @abstractmethod
    async def find_by_tool(
        self,
        tool_id: str,
        limit: int = 100,
    ) -> list[ToolExecutionRecord]:
        ...
