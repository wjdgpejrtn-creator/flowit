from datetime import UTC, datetime
from uuid import uuid4

import pytest
from common_schemas.exceptions import ValidationError

from skills_marketplace.application.use_cases import ApproveSkillUseCase, PublishSkillUseCase
from skills_marketplace.domain.entities import MarketplacePersonalSkill
from skills_marketplace.domain.value_objects import SkillScope, SkillState


class _InMemorySkillRepo:
    def __init__(self) -> None:
        self.personal: dict = {}
        self.team: dict = {}
        self.company: dict = {}
        self.approvals: dict = {}

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

    async def search(self, query_embedding, scope, limit=10, include_promoted=False, lifecycle_state=None):
        return []

    async def save_approval(self, approval):
        self.approvals[approval.approval_id] = approval
        return approval


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
async def test_approve_records_approval_workflow():
    # ADR-0020 (+): reviewer_id/comment를 받기만 하던 것을 ApprovalWorkflow 레코드로 저장 (감사 추적)
    repo = _InMemorySkillRepo()
    sid, reviewer = uuid4(), uuid4()
    await repo.save_personal(_personal(sid, SkillState.REVIEW))

    await ApproveSkillUseCase(repo).execute(sid, SkillScope.PERSONAL, reviewer, approved=True, comment="ok")

    assert len(repo.approvals) == 1
    rec = next(iter(repo.approvals.values()))
    assert rec.skill_id == sid
    assert rec.reviewer_id == reviewer
    assert rec.status == "approved"
    assert rec.comment == "ok"


@pytest.mark.asyncio
async def test_approve_reject_records_rejected_status():
    repo = _InMemorySkillRepo()
    sid, reviewer = uuid4(), uuid4()
    await repo.save_personal(_personal(sid, SkillState.REVIEW))

    await ApproveSkillUseCase(repo).execute(sid, SkillScope.PERSONAL, reviewer, approved=False)

    rec = next(iter(repo.approvals.values()))
    assert rec.status == "rejected"


@pytest.mark.asyncio
async def test_publish_from_draft_raises_invalid_transition():
    repo = _InMemorySkillRepo()
    sid = uuid4()
    await repo.save_personal(_personal(sid, SkillState.DRAFT))

    # DRAFT → PUBLISHED 직접 전이 금지
    with pytest.raises(ValidationError):
        await PublishSkillUseCase(repo).execute(sid, SkillScope.PERSONAL)
