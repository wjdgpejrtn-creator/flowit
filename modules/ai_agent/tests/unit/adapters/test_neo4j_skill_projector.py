"""Neo4jSkillProjector — 게시 스킬 BINDS upsert Cypher 배선 검증 (ADR-0026 Phase 2b).

neo4j 없이 가짜 driver로 발행 Cypher/파라미터를 캡처한다.
"""
from __future__ import annotations

from uuid import uuid4

import pytest
from skills_marketplace.domain.value_objects.skill_scope import SkillScope

from ai_agent.adapters.ontology import Neo4jSkillProjector


class _FakeResult:
    def __aiter__(self):
        async def _gen():
            return
            yield  # pragma: no cover

        return _gen()


class _FakeSession:
    def __init__(self, calls):
        self._calls = calls

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def run(self, query, **params):
        self._calls.append((query, params))
        return _FakeResult()


class _FakeDriver:
    def __init__(self):
        self.calls = []
        self.closed = False

    def session(self):
        return _FakeSession(self.calls)

    async def close(self):
        self.closed = True


@pytest.mark.asyncio
async def test_project_skill_binds_ai_nodes_and_connections():
    driver = _FakeDriver()
    projector = Neo4jSkillProjector(uri="neo4j+s://x", driver_factory=lambda: driver)
    sid = uuid4()

    await projector.project_skill(
        skill_id=sid, scope=SkillScope.TEAM, required_connections=["slack", "slack", "", "gmail"]
    )

    queries = [q for q, _ in driver.calls]
    # 1) BINDS 리셋 + Skill MERGE (tier/audience set)  2) ai 노드 BINDS  3) connection별 BINDS
    assert any("MERGE (s:Skill {id: $skill_id})" in q and "DELETE b" in q for q in queries)
    assert any("MATCH (n:Node {category: 'ai'})" in q for q in queries)
    conn_calls = [p for q, p in driver.calls if ":REQUIRES]->(:Connection {provider: $provider})" in q]
    # 중복 slack 1회 + gmail 1회 = 2회, 빈 문자열 제외
    assert {p["provider"] for p in conn_calls} == {"slack", "gmail"}
    assert len(conn_calls) == 2
    # 모든 Cypher는 skill_id를 문자열로 전달
    assert all(p["skill_id"] == str(sid) for _, p in driver.calls)
    # tier=audience=scope.value
    reset_call = next(p for q, p in driver.calls if "DELETE b" in q)
    assert reset_call["tier"] == "team"
    assert driver.closed is True  # per-request driver 반드시 close


@pytest.mark.asyncio
async def test_project_skill_no_connections_binds_ai_only():
    driver = _FakeDriver()
    projector = Neo4jSkillProjector(uri="neo4j+s://x", driver_factory=lambda: driver)

    await projector.project_skill(skill_id=uuid4(), scope=SkillScope.PERSONAL)

    queries = [q for q, _ in driver.calls]
    assert any("MATCH (n:Node {category: 'ai'})" in q for q in queries)
    assert not any(":Connection {provider: $provider}" in q for q in queries)
    assert driver.closed is True


def test_missing_uri_raises_on_driver_creation(monkeypatch):
    monkeypatch.delenv("NEO4J_URI", raising=False)
    projector = Neo4jSkillProjector(uri=None)
    with pytest.raises(RuntimeError, match="NEO4J_URI"):
        projector._new_driver()
