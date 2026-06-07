"""scripts/build_ontology.py 골격 검증 — 멱등 제약 + 카탈로그 투영 Cypher 배선.

neo4j/Postgres 없이 가짜 session으로 발행 Cypher를 캡처한다 (neo4j는 main()에서만
lazy import, get_all_node_definitions는 _load_node_definitions에서만 import).
"""
import importlib.util
from dataclasses import dataclass
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[5] / "scripts" / "build_ontology.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("build_ontology", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


build_ontology = _load_module()


class _FakeSession:
    def __init__(self):
        self.calls = []

    async def run(self, query, **params):
        self.calls.append((query, params))


@dataclass
class _FakeDef:
    node_type: str
    category: str
    risk_level: str
    service_type: str | None
    name: str
    required_connections: list


def test_script_exists():
    assert _SCRIPT.exists()


@pytest.mark.asyncio
async def test_apply_constraints_runs_all_idempotent_ddl():
    session = _FakeSession()
    await build_ontology.apply_constraints(session)
    assert len(session.calls) == len(build_ontology.CONSTRAINTS)
    assert all("IF NOT EXISTS" in q for q, _ in session.calls)


@dataclass
class _FakeStaging:
    required_connections: list


@dataclass
class _FakeScope:
    value: str


@dataclass
class _FakeSkill:
    skill_id: str
    scope: _FakeScope
    node_spec_staging: _FakeStaging | None


@pytest.mark.asyncio
async def test_project_skill_resets_then_binds_ai_and_connections():
    session = _FakeSession()
    await build_ontology.project_skill(session, "sk-1", "team", ["slack", "slack", "", "gmail"])

    queries = [q for q, _ in session.calls]
    assert any("MERGE (s:Skill {id: $skill_id})" in q and "DELETE b" in q for q in queries)
    assert any("MATCH (n:Node {category: 'ai'})" in q for q in queries)
    conn = [p for q, p in session.calls if ":Connection {provider: $provider}" in q]
    assert {p["provider"] for p in conn} == {"slack", "gmail"}  # dedup + 빈문자 제외
    assert all(p["skill_id"] == "sk-1" for _, p in session.calls)


@pytest.mark.asyncio
async def test_project_skills_backfill_counts_and_uses_scope_tier():
    session = _FakeSession()
    skills = [
        _FakeSkill("sk-1", _FakeScope("personal"), _FakeStaging(["slack"])),
        _FakeSkill("sk-2", _FakeScope("company"), None),
    ]
    count = await build_ontology.project_skills(session, skills)

    assert count == 2
    reset_calls = [p for q, p in session.calls if "DELETE b" in q]
    assert {p["tier"] for p in reset_calls} == {"personal", "company"}


@pytest.mark.asyncio
async def test_project_catalog_merges_node_and_requires():
    session = _FakeSession()
    defs = [
        _FakeDef("slack_send", "messaging", "medium", "slack", "슬랙 전송", ["slack"]),
        _FakeDef("text_transform", "data", "low", None, "텍스트 변환", []),
    ]
    count = await build_ontology.project_catalog(session, defs)

    assert count == 2
    queries = [q for q, _ in session.calls]
    # slack_send: MERGE node 1 + REQUIRES 1 / text_transform: MERGE node 1 + REQUIRES 0
    assert sum("MERGE (n:Node" in q for q in queries) == 2
    assert sum(":REQUIRES]->(c)" in q for q in queries) == 1
    # risk_level은 .value 없으면 str 그대로
    node_call = next(p for q, p in session.calls if "MERGE (n:Node" in q)
    assert node_call["risk_level"] == "medium"
    assert node_call["service_type"] == "slack"
