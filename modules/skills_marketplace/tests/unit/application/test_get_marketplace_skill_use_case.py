"""GetMarketplaceSkillUseCase 단위 테스트.

마켓플레이스(team/company) 스킬 단건 조회 — browse 상세 페이지용. PUBLISHED만 노출(미게시/미존재
동일 404), personal scope 거부(400) 경계를 mock repo로 검증.
"""
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from common_schemas.exceptions import NotFoundError, ValidationError

from skills_marketplace.application.use_cases import GetMarketplaceSkillUseCase
from skills_marketplace.domain.entities import MarketplaceCompanySkill, MarketplaceTeamSkill
from skills_marketplace.domain.value_objects import SkillScope, SkillState


def _company(skill_id, state=SkillState.PUBLISHED):
    now = datetime.now(UTC)
    return MarketplaceCompanySkill(
        skill_id=skill_id, author_id=uuid4(), name="전사 스킬", description="설명",
        lifecycle_state=state, created_at=now, updated_at=now,
    )


def _team(skill_id, state=SkillState.PUBLISHED):
    now = datetime.now(UTC)
    return MarketplaceTeamSkill(
        skill_id=skill_id, team_id=uuid4(), author_id=uuid4(), name="팀 스킬", description="설명",
        lifecycle_state=state, created_at=now, updated_at=now,
    )


class _Repo:
    def __init__(self, company=None, team=None):
        self._company = company
        self._team = team

    async def get_company(self, skill_id):
        return self._company

    async def get_team(self, skill_id):
        return self._team


@pytest.mark.asyncio
async def test_company_published_returns():
    sid = uuid4()
    uc = GetMarketplaceSkillUseCase(_Repo(company=_company(sid)))
    skill = await uc.execute(scope=SkillScope.COMPANY, skill_id=sid)
    assert skill.skill_id == sid


@pytest.mark.asyncio
async def test_team_published_returns():
    sid = uuid4()
    uc = GetMarketplaceSkillUseCase(_Repo(team=_team(sid)))
    skill = await uc.execute(scope=SkillScope.TEAM, skill_id=sid)
    assert skill.skill_id == sid


@pytest.mark.asyncio
async def test_non_published_hidden_as_404():
    # 미게시(draft) 스킬은 id를 알아도 NotFound로 가림 (ADR-0020 (b))
    sid = uuid4()
    uc = GetMarketplaceSkillUseCase(_Repo(company=_company(sid, state=SkillState.DRAFT)))
    with pytest.raises(NotFoundError):
        await uc.execute(scope=SkillScope.COMPANY, skill_id=sid)


@pytest.mark.asyncio
async def test_missing_is_404():
    uc = GetMarketplaceSkillUseCase(_Repo(company=None))
    with pytest.raises(NotFoundError):
        await uc.execute(scope=SkillScope.COMPANY, skill_id=uuid4())


@pytest.mark.asyncio
async def test_personal_scope_rejected():
    uc = GetMarketplaceSkillUseCase(_Repo())
    with pytest.raises(ValidationError):
        await uc.execute(scope=SkillScope.PERSONAL, skill_id=uuid4())
