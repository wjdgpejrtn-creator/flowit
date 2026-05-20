from datetime import UTC, datetime
from uuid import uuid4

import pytest
from common_schemas.exceptions import ValidationError
from skills_marketplace.application.use_cases import ApproveSkillUseCase, PublishSkillUseCase
from skills_marketplace.domain.entities import MarketplacePersonalSkill
from skills_marketplace.domain.value_objects import SkillState
from skills_marketplace.domain.value_objects import SkillScope


class _InMemorySkillRepo:
    def __init__(self) -> None:
        self.personal: dict = {}
        self.team: dict = {}
        self.company: dict = {}

    async def save_personal(self, skill):
        self.personal[skill.skill_id] = skill
        return skill

    async def save_team(self, skill):
        self.team[skill.skill_id] = skill
        return skill

    async def save_company(self, skill):
        self.company[skill.skill_id] = skill
        return skill

    async def get_personal(self, skill_id):
        return self.personal.get(skill_id)

    async def get_team(self, skill_id):
        return self.team.get(skill_id)

    async def get_company(self, skill_id):
        return self.company.get(skill_id)

    async def search(self, query_embedding, scope, limit=10):
        return []


def _personal(skill_id, state):
    now = datetime.now(UTC)
    return MarketplacePersonalSkill(
        skill_id=skill_id,
        owner_user_id=uuid4(),
        name="스킬",
        description="설명",
        node_definition_id=uuid4(),
        lifecycle_state=state,
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_approve_review_to_approved():
    repo = _InMemorySkillRepo()
    sid = uuid4()
    await repo.save_personal(_personal(sid, SkillState.REVIEW))

    await ApproveSkillUseCase(repo).execute(sid, SkillScope.PERSONAL, uuid4(), approved=True)

    updated = await repo.get_personal(sid)
    assert updated.lifecycle_state == SkillState.APPROVED


@pytest.mark.asyncio
async def test_approve_reject_review_to_draft():
    repo = _InMemorySkillRepo()
    sid = uuid4()
    await repo.save_personal(_personal(sid, SkillState.REVIEW))

    await ApproveSkillUseCase(repo).execute(sid, SkillScope.PERSONAL, uuid4(), approved=False)

    updated = await repo.get_personal(sid)
    assert updated.lifecycle_state == SkillState.DRAFT


@pytest.mark.asyncio
async def test_publish_approved_to_published():
    repo = _InMemorySkillRepo()
    sid = uuid4()
    await repo.save_personal(_personal(sid, SkillState.APPROVED))

    await PublishSkillUseCase(repo).execute(sid, SkillScope.PERSONAL)

    updated = await repo.get_personal(sid)
    assert updated.lifecycle_state == SkillState.PUBLISHED


@pytest.mark.asyncio
async def test_publish_from_draft_raises_invalid_transition():
    repo = _InMemorySkillRepo()
    sid = uuid4()
    await repo.save_personal(_personal(sid, SkillState.DRAFT))

    # DRAFT → PUBLISHED 직접 전이 금지
    with pytest.raises(ValidationError):
        await PublishSkillUseCase(repo).execute(sid, SkillScope.PERSONAL)
