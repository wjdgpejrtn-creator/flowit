"""PgMarketplaceSkillRepository.search WHERE 절 단위 테스트 (ADR-0020 ②).

scope별 테이블 선택 + lifecycle/promoted 필터가 SELECT 문에 정확히 반영되는지
DB 실행 없이 컴파일된 SQL로 검증한다 (행 동작 검증은 staging DB 통합 테스트 영역).
"""
from __future__ import annotations

import pytest
from sqlalchemy.dialects import postgresql
from skills_marketplace.domain.value_objects.skill_scope import SkillScope
from skills_marketplace.domain.value_objects.skill_state import SkillState

from storage.repositories.pg_marketplace_skill_repository import PgMarketplaceSkillRepository


class _FakeResult:
    def scalars(self) -> "_FakeResult":
        return self

    def all(self) -> list:
        return []


class _CapturingSession:
    """search가 생성한 SELECT 문을 가로채는 fake AsyncSession."""

    def __init__(self) -> None:
        self.stmt = None

    async def execute(self, stmt):
        self.stmt = stmt
        return _FakeResult()


def _sql(session: _CapturingSession) -> str:
    assert session.stmt is not None, "execute()가 호출되지 않음"
    return str(session.stmt.compile(dialect=postgresql.dialect()))


@pytest.mark.asyncio
async def test_search_personal_excludes_promoted_by_default():
    session = _CapturingSession()
    await PgMarketplaceSkillRepository(session).search([0.0] * 768, SkillScope.PERSONAL)
    sql = _sql(session)
    assert "FROM personal_skills" in sql
    assert "promoted_to_team_id IS NULL" in sql


@pytest.mark.asyncio
async def test_search_team_excludes_promoted_by_default():
    session = _CapturingSession()
    await PgMarketplaceSkillRepository(session).search([0.0] * 768, SkillScope.TEAM)
    sql = _sql(session)
    assert "FROM team_skills" in sql
    assert "promoted_to_company_id IS NULL" in sql


@pytest.mark.asyncio
async def test_search_company_has_no_promoted_filter():
    # company는 최상위 scope — promoted_to_* 컬럼/필터 없음.
    session = _CapturingSession()
    await PgMarketplaceSkillRepository(session).search([0.0] * 768, SkillScope.COMPANY)
    sql = _sql(session)
    assert "FROM company_skills" in sql
    # company는 promoted_to_* 컬럼/필터가 없다 (promoted_from은 SELECT 컬럼이라 무관).
    assert "promoted_to" not in sql


@pytest.mark.asyncio
async def test_search_include_promoted_drops_filter():
    session = _CapturingSession()
    await PgMarketplaceSkillRepository(session).search(
        [0.0] * 768, SkillScope.PERSONAL, include_promoted=True
    )
    assert "promoted_to_team_id IS NULL" not in _sql(session)


@pytest.mark.asyncio
async def test_search_lifecycle_filter_applied():
    session = _CapturingSession()
    await PgMarketplaceSkillRepository(session).search(
        [0.0] * 768, SkillScope.COMPANY, lifecycle_state=SkillState.PUBLISHED
    )
    # WHERE 절에 lifecycle_state 비교가 추가됨 (값은 bind 파라미터).
    assert "lifecycle_state =" in _sql(session)


@pytest.mark.asyncio
async def test_search_no_lifecycle_filter_by_default():
    session = _CapturingSession()
    await PgMarketplaceSkillRepository(session).search([0.0] * 768, SkillScope.COMPANY)
    # lifecycle_state 미지정 → WHERE에 비교 없음 (SELECT 컬럼으로만 등장).
    assert "lifecycle_state =" not in _sql(session)
