from __future__ import annotations

import uuid
from typing import Any, Sequence

from sqlalchemy import select

from src.models.marketplace import SkillReviewModel
from src.models.skill import SkillModel, SkillStatsModel
from src.repositories.base import BaseRepository


class MarketplaceSkillRepository(BaseRepository[SkillModel]):
    async def search(
        self,
        query_embedding: list[float] | None = None,
        tags: list[str] | None = None,
        sort_by: str = "relevance",
        top_k: int = 20,
    ) -> Sequence[SkillModel]:
        stmt = select(self.model).where(
            self.model.lifecycle_state == "approved"
        )

        if tags:
            stmt = stmt.where(self.model.tags.contains(tags))

        if query_embedding and sort_by == "relevance":
            stmt = stmt.order_by(
                self.model.embedding.cosine_distance(query_embedding)
            )
        else:
            stmt = stmt.order_by(self.model.created_at.desc())

        stmt = stmt.limit(top_k)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_with_stats(self, skill_id: uuid.UUID) -> dict[str, Any] | None:
        skill = await self.get(skill_id)
        if skill is None:
            return None
        stats_stmt = select(SkillStatsModel).where(
            SkillStatsModel.skill_id == skill_id
        )
        stats_result = await self.session.execute(stats_stmt)
        stats = stats_result.scalars().first()
        return {"skill": skill, "stats": stats}

    async def submit_review(
        self,
        skill_id: uuid.UUID,
        user_id: uuid.UUID,
        rating: int,
        comment: str | None = None,
    ) -> SkillReviewModel:
        review = SkillReviewModel(
            skill_id=skill_id, user_id=user_id, rating=rating, comment=comment
        )
        self.session.add(review)
        await self.session.flush()
        await self.session.refresh(review)
        return review
