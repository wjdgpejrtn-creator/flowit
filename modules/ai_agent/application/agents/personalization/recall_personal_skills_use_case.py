"""Personalization — 컨텍스트 기반 관련 personal skill 검색.

BGE-M3 코사인 유사도 top-k 반환.
embedding이 없는 항목은 on-the-fly로 계산한다.
"""
from __future__ import annotations

import math
from uuid import UUID

from nodes_graph.domain.ports.embedder_port import EmbedderPort

from ai_agent.domain.entities.personal_skill import PersonalSkill
from ai_agent.domain.ports.personal_memory_store import PersonalMemoryStore


class RecallPersonalSkillsUseCase:
    def __init__(
        self,
        memory_store: PersonalMemoryStore,
        embedder: EmbedderPort,
    ) -> None:
        self._store = memory_store
        self._embedder = embedder

    async def execute(
        self,
        user_id: UUID,
        query: str,
        limit: int = 5,
    ) -> list[PersonalSkill]:
        skills = await self._store.list_entries(user_id)
        if not skills:
            return []

        query_vec = await self._embedder.embed(query)

        scored: list[tuple[float, PersonalSkill]] = []
        for skill in skills:
            if skill.embedding:
                vec = skill.embedding
            else:
                vec = await self._embedder.embed(
                    f"{skill.name} {skill.description} {skill.body}"
                )
            score = _cosine_similarity(query_vec, vec)
            scored.append((score, skill))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [skill for _, skill in scored[:limit]]


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)
