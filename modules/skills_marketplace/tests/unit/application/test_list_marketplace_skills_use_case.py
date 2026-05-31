"""ListMarketplaceSkillsUseCase 단위 테스트.

마켓플레이스 Team/Company 탭 browse 목록(검색어 없는 게시 스킬 나열). 기본 PUBLISHED 필터 +
repo.list_by_scope 위임 + lifecycle override 경계를 mock repo로 검증.
"""
import pytest

from skills_marketplace.application.use_cases import ListMarketplaceSkillsUseCase
from skills_marketplace.domain.value_objects.skill_scope import SkillScope
from skills_marketplace.domain.value_objects.skill_state import SkillState


class _Repo:
    def __init__(self):
        self.captured = {}

    async def list_by_scope(self, scope, lifecycle_state=SkillState.PUBLISHED, limit=50, offset=0):
        self.captured = dict(scope=scope, lifecycle_state=lifecycle_state, limit=limit, offset=offset)
        return []


@pytest.mark.asyncio
async def test_defaults_published_only():
    # ADR-0020 (b): 마켓플레이스 browse는 PUBLISHED만 노출 (미검토 DRAFT/REVIEW 비노출)
    repo = _Repo()
    uc = ListMarketplaceSkillsUseCase(repo)
    await uc.execute(scope=SkillScope.COMPANY)
    assert repo.captured["scope"] == SkillScope.COMPANY
    assert repo.captured["lifecycle_state"] == SkillState.PUBLISHED


@pytest.mark.asyncio
async def test_lifecycle_override_none_returns_all():
    # 관리/디버그: lifecycle_state=None 명시 시 전체 상태
    repo = _Repo()
    uc = ListMarketplaceSkillsUseCase(repo)
    await uc.execute(scope=SkillScope.TEAM, lifecycle_state=None)
    assert repo.captured["scope"] == SkillScope.TEAM
    assert repo.captured["lifecycle_state"] is None


@pytest.mark.asyncio
async def test_pagination_passthrough():
    repo = _Repo()
    uc = ListMarketplaceSkillsUseCase(repo)
    await uc.execute(scope=SkillScope.COMPANY, limit=10, offset=20)
    assert repo.captured["limit"] == 10
    assert repo.captured["offset"] == 20
