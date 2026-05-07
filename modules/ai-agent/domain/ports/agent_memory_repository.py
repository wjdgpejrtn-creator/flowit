from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from ..entities.memory_entry import MemoryEntry


class AgentMemoryRepository(ABC):
    @abstractmethod
    async def save(self, entry: MemoryEntry) -> MemoryEntry: ...

    @abstractmethod
    async def search(self, user_id: UUID, query: str, k: int = 5) -> list[MemoryEntry]: ...

    @abstractmethod
    async def delete(self, entry_id: UUID) -> None: ...
