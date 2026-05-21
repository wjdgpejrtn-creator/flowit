"""ToolsetDispatcher — AI Agent 내부용 toolset 디스패처.

BaseTool(toolset) 11종을 AI Agent LangGraph 노드에서 직접 호출하기 위한 어댑터.
ExecuteToolUseCase를 주입받아 tool_name → execute 위임.

사용 대상: agent 내부 tool-calling (workflow 노드 실행 X — CatalogNodeExecutor 담당, ADR-0018).
composition root(services/agents/*/main.py)에서 ExecuteToolUseCase와 함께 DI 주입.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from common_schemas.security import PermissionSource


class ToolsetDispatcher:
    """AI Agent가 toolset 11종을 직접 호출할 때 사용하는 얇은 어댑터.

    ExecuteToolUseCase(toolset)를 주입받아 dispatch() 한 메서드로 노출.
    타입 힌트에 toolset 직접 의존을 두지 않아 composition root에서만 결합.
    """

    def __init__(self, execute_tool_use_case: Any) -> None:
        self._use_case = execute_tool_use_case

    async def dispatch(
        self,
        tool_name: str,
        input_data: dict[str, Any],
        context: PermissionSource,
        credential_id: UUID | None = None,
        node_id: UUID | None = None,
    ) -> Any:
        """tool_name에 해당하는 BaseTool을 실행하고 ToolOutput을 반환한다."""
        return await self._use_case.execute(
            tool_name=tool_name,
            input_data=input_data,
            context=context,
            credential_id=credential_id,
            node_id=node_id,
        )
