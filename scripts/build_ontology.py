"""온톨로지 ETL — Postgres 노드 카탈로그(+스킬)를 Neo4j 그래프로 투영한다 (ADR-0026 Phase 1).

멱등(MERGE) — 반복 실행해도 중복이 생기지 않는다. 정적 카탈로그는 deploy 훅에서 1회,
스킬은 publish마다 incremental upsert가 맞다(스킬 hook은 박아름 Phase 2, 본 골격은 노드만).

실행:
    NEO4J_URI=neo4j+s://... NEO4J_USERNAME=neo4j NEO4J_PASSWORD=... \
        .venv/Scripts/python.exe scripts/build_ontology.py

노드 소스는 `nodes_graph.application.catalog_registry.get_all_node_definitions()` — import-only
(DB 불필요)로 전체 카탈로그를 준다. 스킬(BINDS, ADR-0026 Phase 2b)은 게시 시 publish 훅이
incremental upsert로 라이브 투영하며(`PublishSkillUseCase` → `Neo4jSkillProjector`), 본
스크립트는 동일 Cypher의 배치 backfill 헬퍼(`project_skill`/`project_skills`)를 제공한다.
"""
from __future__ import annotations

import asyncio
import os
from typing import Any

# 스킬 BINDS Cypher는 라이브 경로(neo4j_skill_projector.py)를 단일 출처로 재사용 — 복붙 drift 방지
# (ADR-0026 Phase 2b). 배치 backfill 헬퍼와 publish 훅이 동일 Cypher를 공유한다.
from ai_agent.adapters.ontology.neo4j_skill_projector import (
    _BIND_AI_NODES as _BIND_SKILL_AI_NODES,
)
from ai_agent.adapters.ontology.neo4j_skill_projector import (
    _BIND_CONNECTION_NODES as _BIND_SKILL_CONNECTION_NODES,
)
from ai_agent.adapters.ontology.neo4j_skill_projector import (
    _RESET_BINDS as _RESET_SKILL_BINDS,
)

# 멱등 스키마 제약/인덱스 (ADR-0026 §1.2). CREATE ... IF NOT EXISTS 라 반복 안전.
CONSTRAINTS: tuple[str, ...] = (
    "CREATE CONSTRAINT node_type_unique IF NOT EXISTS FOR (n:Node) REQUIRE n.node_type IS UNIQUE",
    "CREATE CONSTRAINT skill_id_unique IF NOT EXISTS FOR (s:Skill) REQUIRE s.id IS UNIQUE",
    "CREATE CONSTRAINT connection_provider_unique IF NOT EXISTS "
    "FOR (c:Connection) REQUIRE c.provider IS UNIQUE",
    "CREATE CONSTRAINT category_name_unique IF NOT EXISTS FOR (c:Category) REQUIRE c.name IS UNIQUE",
    "CREATE CONSTRAINT pattern_name_unique IF NOT EXISTS FOR (p:Pattern) REQUIRE p.name IS UNIQUE",
)

_MERGE_NODE = """
MERGE (n:Node {node_type: $node_type})
  SET n.category = $category, n.risk_level = $risk_level,
      n.service_type = $service_type, n.name = $name
MERGE (cat:Category {name: $category})
MERGE (n)-[:IN_CATEGORY]->(cat)
"""

_MERGE_REQUIRES = """
MATCH (n:Node {node_type: $node_type})
MERGE (c:Connection {provider: $provider})
MERGE (n)-[:REQUIRES]->(c)
"""

# 모티프 시드 (ADR-0026 Phase 2a) — 카탈로그 category 기반(DB 불필요, catalog_registry read-only).
# 슬롯은 "generator"(AI 노드)·"evaluator"(condition 노드)로 고정.
# intent는 match_patterns CONTAINS 매칭 대상 — 사용자 문장에서 이 키워드가 검출되면 패턴 활성.
_MERGE_PATTERN = """
MERGE (p:Pattern {name: $name})
SET p.intent = $intent
"""

_MERGE_USES_ROLE = """
MATCH (p:Pattern {name: $pattern_name})
MATCH (n:Node) WHERE n.category = $category
MERGE (p)-[:USES_ROLE {slot: $slot}]->(n)
"""

_PATTERNS: tuple[dict, ...] = (
    {
        "name": "quality_gate_loop",
        "intent": "검증",
        "roles": [
            {"slot": "generator", "category": "ai"},
            {"slot": "evaluator", "category": "condition"},
        ],
    },
)

# 스킬 BINDS 투영 (ADR-0026 Phase 2b) — Cypher 상수는 위에서 라이브 경로(neo4j_skill_projector)
# 를 단일 출처로 import. 라이브는 publish 훅(PublishSkillUseCase → Neo4jSkillProjector) incremental
# upsert, 본 헬퍼는 동일 Cypher로 배치 backfill(스킬 소스 주입 시)을 지원한다.


async def apply_constraints(session: Any) -> None:
    for ddl in CONSTRAINTS:
        await session.run(ddl)


async def project_patterns(session: Any) -> int:
    """_PATTERNS 시드를 (:Pattern)/(:USES_ROLE) 엣지로 투영.

    반환: 투영한 패턴 수.
    """
    for p in _PATTERNS:
        await session.run(_MERGE_PATTERN, name=p["name"], intent=p["intent"])
        for role in p["roles"]:
            await session.run(
                _MERGE_USES_ROLE,
                pattern_name=p["name"],
                category=role["category"],
                slot=role["slot"],
            )
    return len(_PATTERNS)


async def project_catalog(session: Any, node_defs: list[Any]) -> int:
    """노드 카탈로그를 (:Node)/(:Category)/(:Connection) + REQUIRES/IN_CATEGORY로 투영.

    반환: 투영한 노드 수.
    """
    for d in node_defs:
        await session.run(
            _MERGE_NODE,
            node_type=d.node_type,
            category=d.category,
            risk_level=d.risk_level.value if hasattr(d.risk_level, "value") else str(d.risk_level),
            service_type=d.service_type,
            name=d.name,
        )
        for provider in d.required_connections or []:
            await session.run(_MERGE_REQUIRES, node_type=d.node_type, provider=provider)
    return len(node_defs)


async def project_skill(
    session: Any, skill_id: str, tier: str, required_connections: list[str] | None = None
) -> None:
    """게시 스킬 1건을 (:Skill)-[:BINDS]->(:Node)로 멱등 upsert (ADR-0026 Phase 2b).

    모델 A(ADR-0024 D2): 스킬은 ai 카테고리 LLM 노드에 BINDS. 추가로 required_connections가
    있으면 해당 connection을 요구하는 노드에도 BINDS. 재호출 시 기존 BINDS를 재계산(stale 제거).
    """
    await session.run(_RESET_SKILL_BINDS, skill_id=skill_id, tier=tier)
    await session.run(_BIND_SKILL_AI_NODES, skill_id=skill_id)
    for provider in dict.fromkeys(required_connections or []):
        if provider:
            await session.run(_BIND_SKILL_CONNECTION_NODES, skill_id=skill_id, provider=provider)


async def project_skills(session: Any, skills: list[Any]) -> int:
    """게시 스킬 목록을 BINDS로 투영(배치 backfill). 반환: 투영한 스킬 수.

    각 skill은 `skill_id`, `scope`(또는 tier 문자열), `node_spec_staging.required_connections`를
    노출하는 객체. 라이브 incremental upsert는 publish 훅이 담당하므로 본 함수는 backfill 전용.
    """
    for skill in skills:
        scope = getattr(skill, "scope", None)
        tier = getattr(scope, "value", None) or str(scope) if scope is not None else "personal"
        staging = getattr(skill, "node_spec_staging", None)
        required = list(getattr(staging, "required_connections", []) or [])
        await project_skill(session, str(skill.skill_id), tier, required)
    return len(skills)


def _load_node_definitions() -> list[Any]:
    from nodes_graph.application.catalog_registry import get_all_node_definitions

    return get_all_node_definitions()


async def main() -> None:
    uri = os.getenv("NEO4J_URI")
    if not uri:
        raise SystemExit("NEO4J_URI 미설정 — neo4j-uri secret(또는 로컬 env) 필요 (ADR-0026)")

    from neo4j import AsyncGraphDatabase  # lazy — neo4j는 선택 의존

    node_defs = _load_node_definitions()
    driver = AsyncGraphDatabase.driver(
        uri, auth=(os.getenv("NEO4J_USERNAME"), os.getenv("NEO4J_PASSWORD"))
    )
    try:
        async with driver.session() as session:
            await apply_constraints(session)
            count = await project_catalog(session, node_defs)
            pattern_count = await project_patterns(session)
    finally:
        await driver.close()

    print(f"[build_ontology] 제약 {len(CONSTRAINTS)}건 적용 + 노드 {count}건 + 패턴 {pattern_count}건 투영 완료")
    # 스킬 BINDS는 publish 훅(PublishSkillUseCase → Neo4jSkillProjector)이 incremental upsert로
    # 라이브 처리한다(ADR-0026 Phase 2b 완료). 배치 backfill이 필요하면 project_skills()에 DB
    # 스킬 소스를 주입한다(본 import-only main은 DB 비의존이라 미수행). CAN_FOLLOW 추론은 박아름 §4.2.
    print("[build_ontology] 스킬 BINDS = publish 훅 라이브 / 배치 backfill은 project_skills() 사용")


if __name__ == "__main__":
    asyncio.run(main())
