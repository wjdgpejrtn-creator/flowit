"""Personalization — 컨텍스트 기반 관련 memory 검색 (BGE-M3 임베딩 유사도).

Workflow Composer가 프롬프트 작성 전 호출해 관련 사용자 패턴을 주입한다.
"""
from __future__ import annotations

import math
from uuid import UUID

from ....domain.entities.memory_file import MemoryFile
from ....domain.ports.embedding_port import EmbeddingPort
from ....domain.ports.personal_memory_store import PersonalMemoryStore

_DEFAULT_TOP_K = 3
_DEFAULT_MIN_SCORE = 0.5


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


class RecallPersonalSkillsUseCase:
    """BGE-M3 코사인 유사도 기반 개인 memory 검색.

    Returns: 유사도 내림차순 상위 top_k 개의 MemoryFile (min_score 미만 제외).
    """

    def __init__(
        self,
        memory_store: PersonalMemoryStore,
        embedding: EmbeddingPort,
        top_k: int = _DEFAULT_TOP_K,
        min_score: float = _DEFAULT_MIN_SCORE,
    ) -> None:
        self._store = memory_store
        self._embedding = embedding
        self._top_k = top_k
        self._min_score = min_score

    async def execute(self, user_id: UUID, query: str) -> list[MemoryFile]:
        """query와 관련된 사용자 memory 파일을 유사도 순으로 반환."""
        refs = await self._store.load_index(user_id)
        if not refs:
            return []

        query_vec = await self._embedding.embed(query)

        scored: list[tuple[float, MemoryFile]] = []
        for ref in refs:
            emb = await self._store.load_embedding(user_id, ref.name)
            if emb is None:
                # embedding 없으면 해당 파일 로드 후 on-the-fly 생성 + 저장
                try:
                    file = await self._store.load_file(user_id, ref.filename)
                except FileNotFoundError:
                    continue
                emb = await self._embedding.embed(file.body)
                await self._store.save_embedding(user_id, ref.name, emb)
            else:
                try:
                    file = await self._store.load_file(user_id, ref.filename)
                except FileNotFoundError:
                    continue

            score = _cosine_similarity(query_vec, emb)
            if score >= self._min_score:
                scored.append((score, file))

        scored.sort(key=lambda t: t[0], reverse=True)
        return [f for _, f in scored[: self._top_k]]
