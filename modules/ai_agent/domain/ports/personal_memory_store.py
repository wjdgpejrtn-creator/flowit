from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from ai_agent.domain.entities.personal_skill import PersonalSkill


class PersonalMemoryStore(ABC):
    @abstractmethod
    async def load_index(self, user_id: UUID) -> str: ...

    @abstractmethod
    async def save_index(self, user_id: UUID, content: str) -> None: ...

    @abstractmethod
    async def load_entry(self, user_id: UUID, name: str) -> PersonalSkill: ...

    @abstractmethod
    async def save_entry(self, user_id: UUID, skill: PersonalSkill) -> None: ...

    @abstractmethod
    async def list_entries(self, user_id: UUID) -> list[PersonalSkill]: ...
