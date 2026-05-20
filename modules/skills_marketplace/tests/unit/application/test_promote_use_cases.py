from datetime import UTC, datetime
from uuid import uuid4

import pytest

from skills_marketplace.application.use_cases import (
    PromoteToCompanyUseCase,
    PromoteToTeamUseCase,
    SearchSkillsUseCase,
)
from skills_marketplace.domain.entities import MarketplacePersonalSkill
from skills_marketplace.domain.value_objects import SkillScope, SkillState


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

    async def search(self, query_embedding, scope, limit=10, include_promoted=False):
        store = {
            SkillScope.PERSONAL: self.personal,
            SkillScope.TEAM: self.team,
            SkillScope.COMPANY: self.company,
        }[scope]
        results = list(store.values())
        if not include_promoted:
            results = [
                s
                for s in results
                if getattr(s, "promoted_to_team_id", None) is None
                and getattr(s, "promoted_to_company_id", None) is None
            ]
        return results[:limit]


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
    assert team.promoted_from == pid         # 승격 역추적
    assert team.name == "환불 자동화"        # 메타 승계
    assert team.lifecycle_state == SkillState.DRAFT  # 승격 = 재심사 리셋 (게시상태 비승계, 조장 리뷰 #98)
    assert team.tags == ["refund", "cs"]

    # 승격 = 복제(원본 유지) — 원본 personal에 promoted_to_team_id 마킹
    origin = await repo.get_personal(pid)
    assert origin is not None
    assert origin.promoted_to_team_id == new_id


@pytest.mark.asyncio
async def test_search_excludes_promoted_origin_by_default():
    """승격 완료 원본은 search 기본값(include_promoted=False)에서 제외 (중복 노출 방지, 조장 리뷰 #98)."""
    repo = _InMemorySkillRepo()
    pid, owner, team_id = uuid4(), uuid4(), uuid4()
    await repo.save_personal(_personal(pid, owner))

    # 승격 전: personal 검색에 노출
    before = await repo.search([0.1] * 768, SkillScope.PERSONAL)
    assert len(before) == 1

    await PromoteToTeamUseCase(repo).execute(pid, team_id)

    # 승격 후: 기본 검색에서 원본 제외 / include_promoted=True면 포함
    after = await repo.search([0.1] * 768, SkillScope.PERSONAL)
    assert after == []
    assert len(await repo.search([0.1] * 768, SkillScope.PERSONAL, include_promoted=True)) == 1


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
    assert company.lifecycle_state == SkillState.DRAFT  # 재심사 리셋
    # 원본 team에 promoted_to_company_id 마킹 (검색 기본 제외)
    origin_team = await repo.get_team(team_skill_id)
    assert origin_team is not None
    assert origin_team.promoted_to_company_id == company_id


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
