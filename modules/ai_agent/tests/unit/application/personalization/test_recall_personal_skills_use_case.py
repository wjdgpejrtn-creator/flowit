from __future__ import annotations

import pytest
from unittest.mock import AsyncMock
from uuid import uuid4

from ai_agent.application.agents.personalization.recall_personal_skills_use_case import (
    RecallPersonalSkillsUseCase,
    _cosine_similarity,
)
from ai_agent.domain.entities.memory_file import MemoryFile, MemoryFileRef
from ai_agent.domain.ports.embedding_port import EmbeddingPort
from ai_agent.domain.ports.personal_memory_store import PersonalMemoryStore


def _make_ref(name: str) -> MemoryFileRef:
    return MemoryFileRef(filename=f"{name}.md", name=name, description=f"{name} desc")


def _make_file(name: str) -> MemoryFile:
    return MemoryFile(filename=f"{name}.md", name=name, description="", memory_type="feedback", body=f"{name} 내용")


class TestCosineSimilarity:
    def test_identical_vectors(self):
        v = [1.0, 0.0, 0.0]
        assert _cosine_similarity(v, v) == pytest.approx(1.0)

    def test_orthogonal_vectors(self):
        assert _cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)

    def test_opposite_vectors(self):
        assert _cosine_similarity([1.0, 0.0], [-1.0, 0.0]) == pytest.approx(-1.0)

    def test_zero_vector_returns_zero(self):
        assert _cosine_similarity([0.0, 0.0], [1.0, 1.0]) == 0.0


class TestRecallPersonalSkillsUseCase:
    @pytest.mark.asyncio
    async def test_empty_index_returns_empty(self):
        store = AsyncMock(spec=PersonalMemoryStore)
        emb = AsyncMock(spec=EmbeddingPort)
        store.load_index.return_value = []
        uc = RecallPersonalSkillsUseCase(store, emb)
        result = await uc.execute(uuid4(), "쿼리")
        assert result == []
        emb.embed.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_top_k_by_similarity(self):
        uid = uuid4()
        store = AsyncMock(spec=PersonalMemoryStore)
        emb = AsyncMock(spec=EmbeddingPort)

        store.load_index.return_value = [_make_ref("a"), _make_ref("b"), _make_ref("c")]
        store.load_file.side_effect = [_make_file("a"), _make_file("b"), _make_file("c")]
        # 쿼리 embedding = [1, 0, 0]
        emb.embed.return_value = [1.0, 0.0, 0.0]
        # a와 유사, b와 중간, c와 무관
        store.load_embedding.side_effect = [
            [1.0, 0.0, 0.0],  # a: similarity 1.0
            [0.0, 1.0, 0.0],  # b: similarity 0.0
            [1.0, 0.0, 0.0],  # c: similarity 1.0
        ]

        uc = RecallPersonalSkillsUseCase(store, emb, top_k=2, min_score=0.5)
        result = await uc.execute(uid, "관련 쿼리")
        assert len(result) == 2
        assert all(f.name in ("a", "c") for f in result)

    @pytest.mark.asyncio
    async def test_below_min_score_excluded(self):
        uid = uuid4()
        store = AsyncMock(spec=PersonalMemoryStore)
        emb = AsyncMock(spec=EmbeddingPort)

        store.load_index.return_value = [_make_ref("low")]
        store.load_file.return_value = _make_file("low")
        emb.embed.return_value = [1.0, 0.0]
        store.load_embedding.return_value = [0.0, 1.0]  # orthogonal → score 0.0

        uc = RecallPersonalSkillsUseCase(store, emb, top_k=5, min_score=0.5)
        result = await uc.execute(uid, "쿼리")
        assert result == []

    @pytest.mark.asyncio
    async def test_missing_embedding_generates_and_saves(self):
        uid = uuid4()
        store = AsyncMock(spec=PersonalMemoryStore)
        emb = AsyncMock(spec=EmbeddingPort)

        store.load_index.return_value = [_make_ref("no_emb")]
        store.load_file.return_value = _make_file("no_emb")
        store.load_embedding.return_value = None  # no cached embedding
        # embed called twice: once for query, once for file body
        emb.embed.side_effect = [
            [1.0, 0.0],  # query embedding
            [1.0, 0.0],  # file body embedding (on-the-fly)
        ]

        uc = RecallPersonalSkillsUseCase(store, emb, top_k=1, min_score=0.5)
        result = await uc.execute(uid, "쿼리")
        store.save_embedding.assert_called_once()
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_missing_file_is_skipped(self):
        uid = uuid4()
        store = AsyncMock(spec=PersonalMemoryStore)
        emb = AsyncMock(spec=EmbeddingPort)

        store.load_index.return_value = [_make_ref("ghost")]
        store.load_embedding.return_value = [1.0, 0.0]
        store.load_file.side_effect = FileNotFoundError
        emb.embed.return_value = [1.0, 0.0]

        uc = RecallPersonalSkillsUseCase(store, emb, top_k=5, min_score=0.0)
        result = await uc.execute(uid, "쿼리")
        assert result == []
