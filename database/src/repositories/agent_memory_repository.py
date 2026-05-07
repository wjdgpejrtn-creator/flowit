from __future__ import annotations

import uuid
from typing import Sequence

from sqlalchemy import select

from src.models.agent_memory import AgentMemoryModel
from src.repositories.base import BaseRepository


class AgentMemoryRepository(BaseRepository[AgentMemoryModel]):
    async def upsert(self, **kwargs) -> AgentMemoryModel:
        memory_id = kwargs.pop("memory_id", None)
        if memory_id:
            existing = await self.get(memory_id)
            if existing:
                for key, value in kwargs.items():
                    setattr(existing, key, value)
                await self.session.flush()
                await self.session.refresh(existing)
                return existing
        return await self.create(**kwargs)

    async def list_by_user(
        self,
        user_id: uuid.UUID,
        memory_type: str | None = None,
        limit: int = 50,
    ) -> Sequence[AgentMemoryModel]:
        stmt = select(self.model).where(self.model.user_id == user_id)
        if memory_type:
            stmt = stmt.where(self.model.memory_type == memory_type)
        stmt = stmt.order_by(self.model.created_at.desc()).limit(limit)
        result = await self.session.execute(stmt)
        return result.scalars().all()
