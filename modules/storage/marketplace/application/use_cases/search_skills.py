from __future__ import annotations

from ....mappers.skill_mapper import Skill
from ....repositories.pg_skill_repository import PgSkillRepository


class SearchSkillsUseCase:
    def __init__(self, skill_repo: PgSkillRepository, embedder: object) -> None:
        self._skill_repo = skill_repo
        self._embedder = embedder

    async def execute(self, query: str, limit: int = 20) -> list[Skill]:
        query_embedding: list[float] = await self._embedder.embed(query)
        return await self._skill_repo.search(query, query_embedding, limit)
