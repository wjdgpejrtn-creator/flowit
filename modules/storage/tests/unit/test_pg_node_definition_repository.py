"""PgNodeDefinitionRepository.search_by_embedding scope 필터 단위 테스트.

ADR-0020 (i) 가시성 격리는 보안 경계라, viewer 인자에 따라 WHERE 절이
정확히 구성되는지 검증한다. DB 실행 없이 SELECT 문을 가로채 컴파일된 SQL을
점검한다 (행 단위 동작 검증은 staging DB 통합 테스트 영역).
"""
from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy.dialects import postgresql

from storage.repositories.pg_node_definition_repository import PgNodeDefinitionRepository


class _FakeResult:
    def scalars(self) -> "_FakeResult":
        return self

    def all(self) -> list:
        return []


class _CapturingSession:
    """search_by_embedding이 생성한 SELECT 문을 가로채는 fake AsyncSession."""

    def __init__(self) -> None:
        self.stmt = None

    async def execute(self, stmt):
        self.stmt = stmt
        return _FakeResult()


def _compiled_sql(session: _CapturingSession) -> str:
    assert session.stmt is not None, "execute()가 호출되지 않음"
    return str(session.stmt.compile(dialect=postgresql.dialect()))


@pytest.mark.asyncio
async def test_no_viewer_filters_to_global_only():
    # viewer 미지정 → (owner IS NULL AND team IS NULL) = 전역만, personal/team 절 없음.
    session = _CapturingSession()
    await PgNodeDefinitionRepository(session).search_by_embedding([0.0] * 768)
    sql = _compiled_sql(session)
    assert "owner_user_id IS NULL" in sql
    assert "team_id IS NULL" in sql
    assert "owner_user_id =" not in sql
    assert "team_id IN" not in sql


@pytest.mark.asyncio
async def test_viewer_user_id_adds_personal_clause():
    # viewer_user_id 지정 → 전역 절 유지 + personal(owner=viewer) 절 추가.
    session = _CapturingSession()
    await PgNodeDefinitionRepository(session).search_by_embedding(
        [0.0] * 768, viewer_user_id=uuid4()
    )
    sql = _compiled_sql(session)
    assert "owner_user_id IS NULL" in sql
    assert "owner_user_id =" in sql


@pytest.mark.asyncio
async def test_viewer_team_ids_adds_team_clause():
    # viewer_team_ids 지정 → 전역 절 유지 + team(team IN ...) 절 추가.
    session = _CapturingSession()
    await PgNodeDefinitionRepository(session).search_by_embedding(
        [0.0] * 768, viewer_team_ids=[uuid4()]
    )
    sql = _compiled_sql(session)
    assert "owner_user_id IS NULL" in sql
    assert "team_id IN" in sql


@pytest.mark.asyncio
async def test_full_viewer_scope_has_global_personal_team():
    # 전체 viewer 지정 → 전역 + personal + team 세 절 모두 포함.
    session = _CapturingSession()
    await PgNodeDefinitionRepository(session).search_by_embedding(
        [0.0] * 768, viewer_user_id=uuid4(), viewer_team_ids=[uuid4()]
    )
    sql = _compiled_sql(session)
    assert "owner_user_id IS NULL" in sql and "team_id IS NULL" in sql
    assert "owner_user_id =" in sql
    assert "team_id IN" in sql
