from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from ai_agent.application.agents.personalization import LoadUserMemoryUseCase
from ai_agent.domain.entities.personal_skill import PersonalSkill
from ai_agent.domain.ports.personal_memory_store import PersonalMemoryStore


def _skill(skill_type: str, user_id=None) -> PersonalSkill:
    return PersonalSkill(
        user_id=user_id or uuid4(),
        skill_type=skill_type,
        name=f"{skill_type}_skill",
        description=f"{skill_type} 설명",
        body="본문",
    )


class TestLoadUserMemoryUseCase:
    @pytest.mark.asyncio
    async def test_returns_empty_for_no_skills(self):
        store = AsyncMock(spec=PersonalMemoryStore)
        store.list_entries = AsyncMock(return_value=[])
        result = await LoadUserMemoryUseCase(store).execute(uuid4())
        assert result == []

    @pytest.mark.asyncio
    async def test_skill_type_mapped_to_memory_type(self):
        mapping = {
            "user": "preference",
            "feedback": "correction",
            "project": "workflow_pattern",
            "reference": "summary",
        }
        store = AsyncMock(spec=PersonalMemoryStore)
        for skill_type, expected in mapping.items():
            store.list_entries = AsyncMock(return_value=[_skill(skill_type)])
            result = await LoadUserMemoryUseCase(store).execute(uuid4())
            assert result[0].memory_type == expected

    @pytest.mark.asyncio
    async def test_content_contains_name_and_body(self):
        skill = PersonalSkill(
            user_id=uuid4(),
            skill_type="user",
            name="my_role",
            description="역할 설명",
            body="데이터 엔지니어입니다",
        )
        store = AsyncMock(spec=PersonalMemoryStore)
        store.list_entries = AsyncMock(return_value=[skill])
        result = await LoadUserMemoryUseCase(store).execute(skill.user_id)
        assert "my_role" in result[0].content
        assert "데이터 엔지니어입니다" in result[0].content

    @pytest.mark.asyncio
    async def test_multiple_skills_all_converted(self):
        skills = [_skill(t) for t in ("user", "feedback", "project", "reference")]
        store = AsyncMock(spec=PersonalMemoryStore)
        store.list_entries = AsyncMock(return_value=skills)
        result = await LoadUserMemoryUseCase(store).execute(uuid4())
        assert len(result) == 4
