from __future__ import annotations

from uuid import UUID

from ....domain.entities.memory_entry import MemoryEntry
from ....domain.ports.agent_memory_repository import AgentMemoryRepository


class SaveMemoryUseCase:
    def __init__(self, memory_repo: AgentMemoryRepository) -> None:
        self._memory_repo = memory_repo

    async def execute(self, session_id: UUID, entries: list[MemoryEntry]) -> None:
        for entry in entries:
            if not entry.is_ephemeral():
                await self._memory_repo.save(entry)
