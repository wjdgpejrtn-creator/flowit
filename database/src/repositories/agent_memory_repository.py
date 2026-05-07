from __future__ import annotations

import uuid
from typing import Sequence

from sqlalchemy import select, update

from src.models.agent_memory import AgentMemoryModel
from src.repositories.base import BaseRepository


class AgentMemoryRepository(BaseRepository[AgentMemoryModel]):
    async def upsert(self, **kwargs) -> AgentMemoryModel:
        memory_id = kwargs.pop("id", None)
        if memory_id:
            existing = await self.get(memory_id)
            if existing:
                for key, value in kwargs.items():
                    setattr(existing, key, value)
                await self.session.flush()
                await self.session.refresh(existing)
                return existing
        return await self.create(**kwargs)

    async def search_by_embedding(
        self,
        query_vec: list[float],
        scope: str | None = None,
        owner_id: uuid.UUID | None = None,
        top_k: int = 10,
    ) -> Sequence[AgentMemoryModel]:
        stmt = select(self.model)

        if scope:
            stmt = stmt.where(self.model.scope == scope)
        if owner_id:
            stmt = stmt.where(self.model.user_id == owner_id)

        stmt = (
            stmt.order_by(self.model.embedding.cosine_distance(query_vec))
            .limit(top_k)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def decay(self, threshold: float = 0.1) -> int:
        stmt = (
            update(self.model)
            .where(self.model.decay_factor > threshold)
            .values(decay_factor=self.model.decay_factor * 0.95)
        )
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.rowcount
