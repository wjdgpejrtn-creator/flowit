from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from common_schemas import WorkflowSchema

from ai_agent.application.agents.personalization import UpdateUserMemoryUseCase
from ai_agent.application.agents.personalization.update_user_memory_use_case import (
    _SkillExtraction,
    _SkillItem,
)
from ai_agent.domain.ports.llm_port import LLMPort
from ai_agent.domain.ports.personal_memory_store import PersonalMemoryStore
from nodes_graph.domain.ports.embedder_port import EmbedderPort


def _workflow() -> WorkflowSchema:
    return WorkflowSchema(
        workflow_id=uuid4(),
        name="Test",
        scope="private",
        is_draft=True,
        nodes=[],
        connections=[],
    )


def _make_uc(skills: list[_SkillItem], index: str = ""):
    store = AsyncMock(spec=PersonalMemoryStore)
    store.load_index = AsyncMock(return_value=index)
    llm = AsyncMock(spec=LLMPort)
    llm.generate_structured = AsyncMock(return_value=_SkillExtraction(skills=skills))
    embedder = AsyncMock(spec=EmbedderPort)
    embedder.embed = AsyncMock(return_value=[0.0] * 768)
    return UpdateUserMemoryUseCase(store, llm, embedder), store


class TestUpdateUserMemoryUseCase:
    @pytest.mark.asyncio
    async def test_no_skills_extracted_saves_nothing(self):
        uc, store = _make_uc(skills=[])
        await uc.execute(uuid4(), {}, _workflow())
        store.save_entry.assert_not_called()
        store.save_index.assert_not_called()

    @pytest.mark.asyncio
    async def test_extracted_skill_is_saved(self):
        item = _SkillItem(name="role", description="역할", skill_type="user", body="데이터 엔지니어")
        uc, store = _make_uc(skills=[item])
        await uc.execute(uuid4(), {}, _workflow())
        store.save_entry.assert_called_once()

    @pytest.mark.asyncio
    async def test_index_updated_with_new_entry(self):
        item = _SkillItem(name="slack_pref", description="슬랙 선호", skill_type="feedback", body="슬랙 알림")
        uc, store = _make_uc(skills=[item], index="# Memory Index\n")
        await uc.execute(uuid4(), {}, _workflow())
        saved_index: str = store.save_index.call_args[0][1]
        assert "slack_pref" in saved_index

    @pytest.mark.asyncio
    async def test_duplicate_index_entry_not_added_twice(self):
        item = _SkillItem(name="role", description="역할", skill_type="user", body="재추출")
        uc, store = _make_uc(skills=[item], index="# Memory Index\n- [role](role.md) — 역할\n")
        await uc.execute(uuid4(), {}, _workflow())
        saved_index: str = store.save_index.call_args[0][1]
        assert saved_index.count("[role]") == 1
