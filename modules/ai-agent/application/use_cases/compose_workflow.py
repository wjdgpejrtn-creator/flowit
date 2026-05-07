from __future__ import annotations

import asyncio
from uuid import uuid4

from common_schemas import AgentState, PermissionSource
from common_schemas.enums import AgentMode, ExecutionStatus
from common_schemas.exceptions import ExecutionError

from ...domain.ports.agent_graph_port import AgentGraphPort
from ...domain.ports.agent_memory_repository import AgentMemoryRepository
from ...domain.services.memory_summarizer import MemorySummarizer
from ...domain.services.security_guard import SecurityGuard


class ComposeWorkflowUseCase:
    def __init__(
        self,
        security_guard: SecurityGuard,
        graph_runner: AgentGraphPort,
        memory_repo: AgentMemoryRepository,
        memory_summarizer: MemorySummarizer,
    ) -> None:
        self._guard = security_guard
        self._graph = graph_runner
        self._memory_repo = memory_repo
        self._summarizer = memory_summarizer

    async def execute(self, message: str, permission: PermissionSource) -> AgentState:
        self._guard.check(message, permission)

        session_id = uuid4()
        initial_state = AgentState(
            session_id=session_id,
            user_id=permission.user_id,
            messages=[{"role": "user", "content": message}],
            turn_count=0,
            mode=AgentMode.GENERAL,
            execution_status=ExecutionStatus.RUNNING,
        )

        final_state = await self._graph.run(initial_state, permission)

        asyncio.ensure_future(
            self._save_memories(permission.user_id, session_id, final_state)
        )

        return final_state

    async def _save_memories(self, user_id, session_id, state: AgentState) -> None:
        try:
            entries = await self._summarizer.summarize(
                user_id=user_id,
                session_id=session_id,
                messages=state.messages,
            )
            for entry in entries:
                await self._memory_repo.save(entry)
        except Exception:
            pass
