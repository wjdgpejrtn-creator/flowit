import pytest

from skills_marketplace.application.use_cases.search_skills_use_case import SearchSkillsUseCase
from skills_marketplace.domain.value_objects.skill_state import SkillState


class _Repo:
    def __init__(self):
        self.captured = {}

    async def search(self, query_embedding, scope, limit=10, include_promoted=False, lifecycle_state=None):
        self.captured = dict(scope=scope, limit=limit, lifecycle_state=lifecycle_state)
        return []


@pytest.mark.asyncio
async def test_search_defaults_published_only():
    # ADR-0020 (b): Composer 검색은 PUBLISHED만 노출 (미검토 DRAFT/REVIEW 오염 방지)
    repo = _Repo()
    uc = SearchSkillsUseCase(repo)
    await uc.execute([0.1] * 768)
    assert repo.captured["lifecycle_state"] == SkillState.PUBLISHED


@pytest.mark.asyncio
async def test_search_lifecycle_override_none_returns_all():
    # 관리/디버그용: lifecycle_state=None 명시 시 전체 상태 검색
    repo = _Repo()
    uc = SearchSkillsUseCase(repo)
    await uc.execute([0.1] * 768, lifecycle_state=None)
    assert repo.captured["lifecycle_state"] is None
