from datetime import UTC, datetime
from uuid import uuid4

import pytest
from skills_marketplace.application.use_cases import (
    PromoteToCompanyUseCase,
    PromoteToTeamUseCase,
    SearchSkillsUseCase,
)
from skills_marketplace.domain.entities import (
    MarketplaceCompanySkill,
    MarketplacePersonalSkill,
    MarketplaceTeamSkill,
)
from skills_marketplace.domain.value_objects import SkillState
from skills_marketplace.domain.value_objects import SkillScope


class _InMemorySkillRepo:
    """inline 헬퍼 — SkillRepository ABC In-Memory 구현 (테스트 전용)."""

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
        store = {SkillScope.PERSONAL: self.personal, SkillScope.TEAM: self.team, SkillScope.COMPANY: self.company}[scope]
        return list(store.values())[:limit]


def _personal(skill_id, owner_id):
    now = datetime.now(UTC)
    return MarketplacePersonalSkill(
        skill_id=skill_id,
        owner_user_id=owner_id,
        name="환불 자동화",
        description="환불 요청 처리 스킬",
        node_definition_id=uuid4(),
        lifecycle_state=SkillState.PUBLISHED,
        tags=["refund", "cs"],
        version="1.0.0",
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_promote_personal_to_team_creates_team_skill():
    repo = _InMemorySkillRepo()
    pid, owner = uuid4(), uuid4()
    await repo.save_personal(_personal(pid, owner))

    team_id = uuid4()
    new_id = await PromoteToTeamUseCase(repo).execute(pid, team_id)

    team = await repo.get_team(new_id)
    assert team is not None
    assert team.team_id == team_id
    assert team.author_id == owner          # 원작성자 승계
    assert team.promoted_from == pid         # 승격 추적
    assert team.name == "환불 자동화"        # 메타 승계
    assert team.lifecycle_state == SkillState.PUBLISHED  # 게시상태 승계
    assert team.tags == ["refund", "cs"]


@pytest.mark.asyncio
async def test_promote_team_to_company_creates_company_skill():
    repo = _InMemorySkillRepo()
    pid, owner, team_id = uuid4(), uuid4(), uuid4()
    await repo.save_personal(_personal(pid, owner))
    team_skill_id = await PromoteToTeamUseCase(repo).execute(pid, team_id)

    company_id = await PromoteToCompanyUseCase(repo).execute(team_skill_id)

    company = await repo.get_company(company_id)
    assert company is not None
    assert company.author_id == owner
    assert company.promoted_from == team_skill_id


@pytest.mark.asyncio
async def test_promote_nonexistent_personal_raises():
    from common_schemas.exceptions import NotFoundError

    repo = _InMemorySkillRepo()
    with pytest.raises(NotFoundError):
        await PromoteToTeamUseCase(repo).execute(uuid4(), uuid4())


@pytest.mark.asyncio
async def test_search_delegates_to_repo():
    repo = _InMemorySkillRepo()
    pid, owner = uuid4(), uuid4()
    await repo.save_personal(_personal(pid, owner))

    results = await SearchSkillsUseCase(repo).execute([0.1] * 768, SkillScope.PERSONAL, limit=5)
    assert len(results) == 1
    assert results[0].skill_id == pid
