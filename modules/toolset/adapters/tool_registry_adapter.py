from __future__ import annotations

from uuid import UUID

from common_schemas.exceptions import NotFoundError

from ..domain.entities.base_tool import BaseTool
from ..domain.entities.tool_metadata import ToolMetadata
from ..domain.exceptions import ConflictError
from ..domain.ports.tool_registry import ToolRegistry


class ToolRegistryAdapter(ToolRegistry):
    """ToolRegistry Port의 인메모리 구현체.

    앱 시작 시 register_tool() 또는 register_bulk()로 도구를 등록한다.
    DI 컨테이너에서 싱글턴으로 관리.
    """

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}
        self._metadata: dict[str, ToolMetadata] = {}

    # ── Port ABC 구현 ──────────────────────────────────────────────────────

    def get(self, tool_name: str) -> BaseTool:
        if tool_name not in self._tools:
            raise NotFoundError(
                message=f"Tool '{tool_name}' is not registered. "
                        f"Available: {list(self._tools.keys())}",
                code="E_NODE_TYPE_MISMATCH",
            )
        return self._tools[tool_name]

    def list_all(self) -> list[ToolMetadata]:
        return list(self._metadata.values())

    def list_by_category(self, category: str) -> list[ToolMetadata]:
        return [m for m in self._metadata.values() if m.category == category]

    # ── 어댑터 전용 (DI 조립용) ────────────────────────────────────────────

    def register_tool(
        self,
        tool: BaseTool,
        tool_id: UUID,
        version: str,
        category: str,
        overwrite: bool = True,
    ) -> None:
        """도구 등록. overwrite=False면 중복 tool_name 시 ConflictError."""
        if not overwrite and tool.name in self._tools:
            raise ConflictError(
                message=f"Tool '{tool.name}' is already registered.",
                code="E_DUPLICATE_ID",
            )
        self._tools[tool.name] = tool
        self._metadata[tool.name] = ToolMetadata.from_tool(
            tool, tool_id=tool_id, version=version, category=category,
        )

    def register_bulk(self, tools: list[tuple[BaseTool, UUID, str, str]]) -> None:
        """일괄 등록. (tool, tool_id, version, category) 튜플 리스트."""
        for tool, tool_id, version, category in tools:
            self.register_tool(tool, tool_id, version, category)

    def __len__(self) -> int:
        return len(self._tools)
