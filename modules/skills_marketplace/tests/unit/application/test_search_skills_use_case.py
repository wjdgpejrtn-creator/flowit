from uuid import uuid4

import pytest

from skills_marketplace.application.use_cases.search_skills_use_case import SearchSkillsUseCase
from skills_marketplace.domain.value_objects.skill_scope import SkillScope
from skills_marketplace.domain.value_objects.skill_state import SkillState


class _Repo:
    """search 호출을 스코프별로 기록하고 미리 설정한 결과를 돌려주는 가짜 repo."""

    def __init__(self, results: dict | None = None):
        self.captured: dict = {}
        self.calls: list[dict] = []
        self._results = results or {}

    async def search(
        self,
        query_embedding,
        scope,
        limit=10,
        include_promoted=False,
        lifecycle_state=None,
        owner_user_id=None,
        max_distance=None,
    ):
        call = dict(
            scope=scope,
            limit=limit,
            include_promoted=include_promoted,
            lifecycle_state=lifecycle_state,
            owner_user_id=owner_user_id,
            max_distance=max_distance,
        )
        self.captured = call
        self.calls.append(call)
        return list(self._results.get(scope, []))


class _Skill:
    def __init__(self, skill_id):
        self.skill_id = skill_id


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


@pytest.mark.asyncio
async def test_execute_forwards_owner_and_max_distance():
    repo = _Repo()
    uc = SearchSkillsUseCase(repo)
    uid = uuid4()
    await uc.execute([0.1] * 768, scope=SkillScope.PERSONAL, owner_user_id=uid, max_distance=0.3)
    assert repo.captured["owner_user_id"] == uid
    assert repo.captured["max_distance"] == 0.3


@pytest.mark.asyncio
async def test_execute_accessible_searches_personal_owned_and_company():
    repo = _Repo()
    uc = SearchSkillsUseCase(repo)
    uid = uuid4()
    await uc.execute_accessible([0.1] * 768, user_id=uid, max_distance=0.3)

    scopes = {c["scope"]: c for c in repo.calls}
    assert SkillScope.PERSONAL in scopes and SkillScope.COMPANY in scopes
    # personal은 소유자 인가 필터가 반드시 걸려야 한다 (IDOR 차단)
    assert scopes[SkillScope.PERSONAL]["owner_user_id"] == uid
    # company는 전사 범위라 owner 필터 없음
    assert scopes[SkillScope.COMPANY]["owner_user_id"] is None
    # 관련성 컷이 두 스코프 모두에 전달
    assert scopes[SkillScope.PERSONAL]["max_distance"] == 0.3
    assert scopes[SkillScope.COMPANY]["max_distance"] == 0.3
    # owner 본인 personal 검색은 승격(=복제)한 자기 스킬도 포함해야 한다 — promote 후에도
    # compose 후보로 계속 노출(team scope 미검색이라 기본 제외 시 영구 비가시).
    assert scopes[SkillScope.PERSONAL]["include_promoted"] is True
    # company는 승격 원본 중복 노출 방지 위해 기본 제외 유지
    assert scopes[SkillScope.COMPANY]["include_promoted"] is False


@pytest.mark.asyncio
async def test_execute_accessible_merges_roundrobin_and_dedups():
    dup = uuid4()
    p1, c1 = _Skill(uuid4()), _Skill(uuid4())
    shared_p, shared_c = _Skill(dup), _Skill(dup)  # 동일 skill_id → 1개만
    repo = _Repo(results={
        SkillScope.PERSONAL: [p1, shared_p],
        SkillScope.COMPANY: [c1, shared_c],
    })
    uc = SearchSkillsUseCase(repo)
    merged = await uc.execute_accessible([0.1] * 768, user_id=uuid4(), limit=5)

    ids = [s.skill_id for s in merged]
    # 라운드로빈: personal 먼저, 그다음 company
    assert ids[0] == p1.skill_id
    assert ids[1] == c1.skill_id
    # 중복 skill_id는 1회만
    assert ids.count(dup) == 1


@pytest.mark.asyncio
async def test_execute_accessible_respects_limit():
    repo = _Repo(results={
        SkillScope.PERSONAL: [_Skill(uuid4()) for _ in range(5)],
        SkillScope.COMPANY: [_Skill(uuid4()) for _ in range(5)],
    })
    uc = SearchSkillsUseCase(repo)
    merged = await uc.execute_accessible([0.1] * 768, user_id=uuid4(), limit=3)
    assert len(merged) == 3
