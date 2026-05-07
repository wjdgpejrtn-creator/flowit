from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from ..entities.memory_entry import MemoryEntry


class AgentMemoryRepository(ABC):
    @abstractmethod
    async def save(self, entry: MemoryEntry) -> None: ...

    @abstractmethod
    async def find_by_user(self, user_id: UUID, limit: int = 20) -> list[MemoryEntry]: ...

    @abstractmethod
    async def find_by_session(self, session_id: UUID, limit: int = 20) -> list[MemoryEntry]: ...
