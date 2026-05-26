from datetime import UTC, datetime
from uuid import uuid4

import pytest
from common_schemas.exceptions import AuthorizationError, NotFoundError, ValidationError

from skills_marketplace.application.use_cases import ApproveSkillUseCase, PublishSkillUseCase, SubmitSkillUseCase
from skills_marketplace.domain.entities import MarketplacePersonalSkill, MarketplaceTeamSkill
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


class _NodeDefRepo:
    async def upsert(self, node_def):
        return node_def


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


def _team(skill_id, state, team_id):
    now = datetime.now(UTC)
    return MarketplaceTeamSkill(
        skill_id=skill_id,
        team_id=team_id,
        author_id=uuid4(),
        name="팀스킬",
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
    skill = _personal(sid, SkillState.REVIEW)
    await repo.save_personal(skill)

    # personal self-review: actor(reviewer) == owner
    await ApproveSkillUseCase(repo).execute(
        sid, SkillScope.PERSONAL, skill.owner_user_id, approved=True, actor_role="User"
    )

    updated = await repo.get_personal(sid)
    assert updated.lifecycle_state == SkillState.APPROVED


@pytest.mark.asyncio
async def test_approve_reject_review_to_draft():
    repo = _InMemorySkillRepo()
    sid = uuid4()
    skill = _personal(sid, SkillState.REVIEW)
    await repo.save_personal(skill)

    await ApproveSkillUseCase(repo).execute(
        sid, SkillScope.PERSONAL, skill.owner_user_id, approved=False, actor_role="User"
    )

    updated = await repo.get_personal(sid)
    assert updated.lifecycle_state == SkillState.DRAFT


@pytest.mark.asyncio
async def test_publish_approved_to_published():
    repo = _InMemorySkillRepo()
    sid = uuid4()
    skill = _personal(sid, SkillState.APPROVED)
    await repo.save_personal(skill)

    await PublishSkillUseCase(repo, _NodeDefRepo()).execute(
        sid, SkillScope.PERSONAL, actor_user_id=skill.owner_user_id, actor_role="User"
    )

    updated = await repo.get_personal(sid)
    assert updated.lifecycle_state == SkillState.PUBLISHED


@pytest.mark.asyncio
async def test_approve_records_approval_workflow():
    # ADR-0020 (+): reviewer_id/comment를 받기만 하던 것을 ApprovalWorkflow 레코드로 저장 (감사 추적)
    repo = _InMemorySkillRepo()
    sid = uuid4()
    skill = _personal(sid, SkillState.REVIEW)
    await repo.save_personal(skill)
    reviewer = skill.owner_user_id  # personal: actor == owner

    await ApproveSkillUseCase(repo).execute(
        sid, SkillScope.PERSONAL, reviewer, approved=True, comment="ok", actor_role="User"
    )

    assert len(repo.approvals) == 1
    rec = next(iter(repo.approvals.values()))
    assert rec.skill_id == sid
    assert rec.reviewer_id == reviewer
    assert rec.status == "approved"
    assert rec.comment == "ok"
    assert rec.scope == SkillScope.PERSONAL  # 조장 A안: skill_approvals.scope NOT NULL 충족 (감사 레코드에 scope 명시)


@pytest.mark.asyncio
async def test_approve_reject_records_rejected_status():
    repo = _InMemorySkillRepo()
    sid = uuid4()
    skill = _personal(sid, SkillState.REVIEW)
    await repo.save_personal(skill)

    await ApproveSkillUseCase(repo).execute(
        sid, SkillScope.PERSONAL, skill.owner_user_id, approved=False, actor_role="User"
    )

    rec = next(iter(repo.approvals.values()))
    assert rec.status == "rejected"


@pytest.mark.asyncio
async def test_publish_from_draft_raises_invalid_transition():
    repo = _InMemorySkillRepo()
    sid = uuid4()
    skill = _personal(sid, SkillState.DRAFT)
    await repo.save_personal(skill)

    # 인가 통과(owner)했지만 DRAFT → PUBLISHED 직접 전이 금지
    with pytest.raises(ValidationError):
        await PublishSkillUseCase(repo, _NodeDefRepo()).execute(
            sid, SkillScope.PERSONAL, actor_user_id=skill.owner_user_id, actor_role="User"
        )


# ── ADR-0020 위임2: actor 인가 enforcement ──────────────────────────────────


@pytest.mark.asyncio
async def test_approve_personal_rejects_non_owner():
    repo = _InMemorySkillRepo()
    sid = uuid4()
    skill = _personal(sid, SkillState.REVIEW)
    await repo.save_personal(skill)

    # 소유자가 아닌 actor → 인가 거부 + 상태 미변경
    with pytest.raises(AuthorizationError):
        await ApproveSkillUseCase(repo).execute(
            sid, SkillScope.PERSONAL, uuid4(), approved=True, actor_role="User"
        )
    assert (await repo.get_personal(sid)).lifecycle_state == SkillState.REVIEW


@pytest.mark.asyncio
async def test_publish_team_manager_same_dept_authorized():
    repo = _InMemorySkillRepo()
    sid, dept = uuid4(), uuid4()
    await repo.save_team(_team(sid, SkillState.APPROVED, team_id=dept))

    await PublishSkillUseCase(repo, _NodeDefRepo()).execute(
        sid, SkillScope.TEAM, actor_user_id=uuid4(), actor_role="team_manager", actor_department_id=dept
    )

    assert (await repo.get_team(sid)).lifecycle_state == SkillState.PUBLISHED


@pytest.mark.asyncio
async def test_publish_team_non_manager_denied():
    repo = _InMemorySkillRepo()
    sid, dept = uuid4(), uuid4()
    await repo.save_team(_team(sid, SkillState.APPROVED, team_id=dept))

    # 같은 부서지만 team_manager 아님 → 거부 + 상태 미변경
    with pytest.raises(AuthorizationError):
        await PublishSkillUseCase(repo, _NodeDefRepo()).execute(
            sid, SkillScope.TEAM, actor_user_id=uuid4(), actor_role="User", actor_department_id=dept
        )
    assert (await repo.get_team(sid)).lifecycle_state == SkillState.APPROVED


@pytest.mark.asyncio
async def test_submit_draft_to_review():
    # ADR-0020 Q4 (PR #150 위임): DRAFT → REVIEW 검토 제출
    repo = _InMemorySkillRepo()
    sid = uuid4()
    await repo.save_personal(_personal(sid, SkillState.DRAFT))

    await SubmitSkillUseCase(repo).execute(sid, SkillScope.PERSONAL)

    updated = await repo.get_personal(sid)
    assert updated.lifecycle_state == SkillState.REVIEW


@pytest.mark.asyncio
async def test_submit_published_raises_invalid_transition():
    repo = _InMemorySkillRepo()
    sid = uuid4()
    await repo.save_personal(_personal(sid, SkillState.PUBLISHED))

    # PUBLISHED → REVIEW 전이 금지 (DRAFT에서만 submit 가능)
    with pytest.raises(ValidationError):
        await SubmitSkillUseCase(repo).execute(sid, SkillScope.PERSONAL)


@pytest.mark.asyncio
async def test_submit_not_found_raises():
    repo = _InMemorySkillRepo()
    with pytest.raises(NotFoundError):
        await SubmitSkillUseCase(repo).execute(uuid4(), SkillScope.PERSONAL)
