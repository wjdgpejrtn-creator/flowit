from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from ai_agent.application.agents.personalization import RecallPersonalSkillsUseCase
from ai_agent.domain.entities.personal_skill import PersonalSkill
from ai_agent.domain.ports.personal_memory_store import PersonalMemoryStore
from nodes_graph.domain.ports.embedder_port import EmbedderPort


def _skill(name: str, embedding: list[float] | None = None) -> PersonalSkill:
    return PersonalSkill(
        user_id=uuid4(),
        skill_type="user",
        name=name,
        description=f"{name} 설명",
        body="본문",
        embedding=embedding,
    )


class TestRecallPersonalSkillsUseCase:
    @pytest.mark.asyncio
    async def test_returns_empty_when_no_skills(self):
        store = AsyncMock(spec=PersonalMemoryStore)
        store.list_entries = AsyncMock(return_value=[])
        embedder = AsyncMock(spec=EmbedderPort)
        result = await RecallPersonalSkillsUseCase(store, embedder).execute(uuid4(), "슬랙")
        assert result == []
        embedder.embed.assert_not_called()

    @pytest.mark.asyncio
    async def test_uses_precomputed_embedding(self):
        vec = [1.0, 0.0, 0.0]
        skill = _skill("slack", embedding=vec)
        store = AsyncMock(spec=PersonalMemoryStore)
        store.list_entries = AsyncMock(return_value=[skill])
        embedder = AsyncMock(spec=EmbedderPort)
        embedder.embed = AsyncMock(return_value=vec)
        await RecallPersonalSkillsUseCase(store, embedder).execute(uuid4(), "슬랙", limit=1)
        # query용 1회만 embed 호출 (precomputed embedding은 그대로 사용)
        assert embedder.embed.call_count == 1

    @pytest.mark.asyncio
    async def test_embeds_skill_on_the_fly_when_no_embedding(self):
        skill = _skill("gmail")  # embedding=None
        store = AsyncMock(spec=PersonalMemoryStore)
        store.list_entries = AsyncMock(return_value=[skill])
        embedder = AsyncMock(spec=EmbedderPort)
        embedder.embed = AsyncMock(return_value=[1.0, 0.0, 0.0])
        await RecallPersonalSkillsUseCase(store, embedder).execute(uuid4(), "이메일", limit=1)
        # query + skill on-the-fly = 2회
        assert embedder.embed.call_count == 2

    @pytest.mark.asyncio
    async def test_top_k_limit(self):
        skills = [_skill(f"skill_{i}", embedding=[float(i), 0.0, 0.0]) for i in range(5)]
        store = AsyncMock(spec=PersonalMemoryStore)
        store.list_entries = AsyncMock(return_value=skills)
        embedder = AsyncMock(spec=EmbedderPort)
        embedder.embed = AsyncMock(return_value=[1.0, 0.0, 0.0])
        result = await RecallPersonalSkillsUseCase(store, embedder).execute(uuid4(), "test", limit=3)
        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_sorted_by_cosine_similarity_descending(self):
        # high: [1,0,0] vs query [1,0,0] → cosine 1.0
        # low:  [0,1,0] vs query [1,0,0] → cosine 0.0
        high = _skill("high", embedding=[1.0, 0.0, 0.0])
        low = _skill("low", embedding=[0.0, 1.0, 0.0])
        store = AsyncMock(spec=PersonalMemoryStore)
        store.list_entries = AsyncMock(return_value=[low, high])
        embedder = AsyncMock(spec=EmbedderPort)
        embedder.embed = AsyncMock(return_value=[1.0, 0.0, 0.0])
        result = await RecallPersonalSkillsUseCase(store, embedder).execute(uuid4(), "쿼리", limit=2)
        assert result[0].name == "high"
        assert result[1].name == "low"
