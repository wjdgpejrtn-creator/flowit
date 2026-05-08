from __future__ import annotations

import uuid
from typing import Sequence

from sqlalchemy import select, update

from src.models.skill import SkillModel
from src.repositories.base import BaseRepository


class SkillRepository(BaseRepository[SkillModel]):
    async def approve(self, skill_id: uuid.UUID) -> None:
        stmt = (
            update(self.model)
            .where(self.model.skill_id == skill_id)
            .values(lifecycle_state="approved")
        )
        await self.session.execute(stmt)
        await self.session.flush()

    async def search(self, query_embedding: list[float], top_k: int = 10) -> Sequence[SkillModel]:
        stmt = (
            select(self.model)
            .order_by(self.model.embedding.cosine_distance(query_embedding))
            .limit(top_k)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()
