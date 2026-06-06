"""온톨로지 ETL — Postgres 노드 카탈로그(+스킬)를 Neo4j 그래프로 투영한다 (ADR-0026 Phase 1).

멱등(MERGE) — 반복 실행해도 중복이 생기지 않는다. 정적 카탈로그는 deploy 훅에서 1회,
스킬은 publish마다 incremental upsert가 맞다(스킬 hook은 박아름 Phase 2, 본 골격은 노드만).

실행:
    NEO4J_URI=neo4j+s://... NEO4J_USERNAME=neo4j NEO4J_PASSWORD=... \
        .venv/Scripts/python.exe scripts/build_ontology.py

노드 소스는 `nodes_graph.application.catalog_registry.get_all_node_definitions()` — import-only
(DB 불필요)로 전체 카탈로그를 준다. 스킬(BINDS)은 DB 의존이라 Phase 1에서는 미투영(TODO).
"""
from __future__ import annotations

import asyncio
import os
from typing import Any

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


async def apply_constraints(session: Any) -> None:
    for ddl in CONSTRAINTS:
        await session.run(ddl)


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


def _load_node_definitions() -> list[Any]:
    from nodes_graph.application.catalog_registry import get_all_node_definitions

    return get_all_node_definitions()


async def main() -> None:
    uri = os.getenv("NEO4J_URI")
    if not uri:
        raise SystemExit("NEO4J_URI 미설정 — ontology-neo4j-auradb secret 바인딩 필요 (ADR-0026)")

    from neo4j import AsyncGraphDatabase  # lazy — neo4j는 선택 의존

    node_defs = _load_node_definitions()
    driver = AsyncGraphDatabase.driver(
        uri, auth=(os.getenv("NEO4J_USERNAME"), os.getenv("NEO4J_PASSWORD"))
    )
    try:
        async with driver.session() as session:
            await apply_constraints(session)
            count = await project_catalog(session, node_defs)
    finally:
        await driver.close()

    print(f"[build_ontology] 제약 {len(CONSTRAINTS)}건 적용 + 노드 {count}건 투영 완료")
    print("[build_ontology] TODO(Phase 2/박아름): 스킬 BINDS incremental upsert + CAN_FOLLOW 추론")


if __name__ == "__main__":
    asyncio.run(main())
