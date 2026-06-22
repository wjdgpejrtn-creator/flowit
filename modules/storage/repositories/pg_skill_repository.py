from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from common_schemas.exceptions import NotFoundError

from ..mappers.skill_mapper import Skill, SkillMapper
from ..orm.skill_model import SkillModel


class PgSkillRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert(self, skill: Skill) -> Skill:
        model = SkillMapper.to_orm(skill)
        model.search_vector = func.to_tsvector("korean", func.concat(skill.name, " ", skill.description))
        merged = await self._session.merge(model)
        await self._session.flush()
        return SkillMapper.to_domain(merged)

    async def get_by_id(self, skill_id: UUID) -> Skill:
        stmt = select(SkillModel).where(SkillModel.skill_id == skill_id)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            raise NotFoundError(f"Skill not found: {skill_id}", code="E-SKILL-001")
        return SkillMapper.to_domain(model)

    async def list(self, limit: int = 50, offset: int = 0) -> list[Skill]:
        stmt = select(SkillModel).order_by(SkillModel.updated_at.desc()).limit(limit).offset(offset)
        result = await self._session.execute(stmt)
        return [SkillMapper.to_domain(row) for row in result.scalars().all()]

    async def search(self, query: str, query_embedding: list[float], limit: int = 20) -> list[Skill]:
        """하이브리드 검색: 0.4 * FTS + 0.6 * vector similarity"""
        stmt = (
            select(
                SkillModel,
                (
                    0.4 * func.coalesce(func.ts_rank(SkillModel.search_vector, func.plainto_tsquery("korean", query)), 0)
                    + 0.6 * (1 - SkillModel.embedding.cosine_distance(query_embedding))
                ).label("score"),
            )
            .where(SkillModel.lifecycle_state == "published", SkillModel.embedding.isnot(None))
            .order_by(text("score DESC"))
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return [SkillMapper.to_domain(row[0]) for row in result.all()]
