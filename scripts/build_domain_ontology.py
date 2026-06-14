"""도메인 그라운딩 ETL — `seeds/domains/*.json`을 Neo4j 도메인 서브그래프로 투영 (ADR-0029).

skill builder 전용. composer ETL(`build_ontology.py`)과 **완전 별개** — 같은 Neo4j를 쓰되
`(:Domain)/(:Playbook)/(:Stage)/(:Rule)` 라벨만 투영하고 composer 라벨(:Node/:Skeleton/
:Pattern)은 한 줄도 건드리지 않는다. 노드는 엣지가 아니라 node_type 문자열로 보유하며
`EXECUTABLE_NODE_TYPES`로 검증한다(환각 차단).

실행:
    NEO4J_URI=neo4j+s://... NEO4J_USERNAME=neo4j NEO4J_PASSWORD=... \
        .venv/Scripts/python.exe scripts/build_domain_ontology.py
"""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any

from ai_agent.domain.value_objects.domain_grounding import Domain, parse_domain

_SEEDS_DIR = Path(__file__).resolve().parents[1] / "modules" / "ai_agent" / "seeds" / "domains"

# 도메인 서브그래프 제약(멱등). composer 제약과 라벨이 안 겹친다.
CONSTRAINTS: tuple[str, ...] = (
    "CREATE CONSTRAINT domain_code_unique IF NOT EXISTS FOR (d:Domain) REQUIRE d.code IS UNIQUE",
    "CREATE CONSTRAINT playbook_id_unique IF NOT EXISTS FOR (p:Playbook) REQUIRE p.id IS UNIQUE",
    "CREATE CONSTRAINT stage_id_unique IF NOT EXISTS FOR (s:Stage) REQUIRE s.id IS UNIQUE",
    "CREATE CONSTRAINT rule_id_unique IF NOT EXISTS FOR (r:Rule) REQUIRE r.id IS UNIQUE",
)

# 전 재투영 — 도메인 서브그래프(4 라벨)만 통째 삭제 후 재생성. composer 라벨은 미포함이라 안전.
_RESET_DOMAINS = "MATCH (n) WHERE n:Domain OR n:Playbook OR n:Stage OR n:Rule DETACH DELETE n"

_MERGE_DOMAIN = """
MERGE (d:Domain {code: $code})
SET d.name = $name, d.kind = $kind, d.description = $description
"""

_CREATE_RULE_ON_DOMAIN = """
MATCH (d:Domain {code: $code})
CREATE (d)-[:HAS_RULE]->(:Rule {
  id: $id, kind: $kind, statement: $statement,
  node_type: $node_type, rationale: $rationale, severity: $severity})
"""

_MERGE_PLAYBOOK = """
MATCH (d:Domain {code: $code})
MERGE (p:Playbook {id: $id})
SET p.name = $name, p.intent = $intent, p.summary = $summary
MERGE (d)-[:HAS_PLAYBOOK]->(p)
"""

_CREATE_RULE_ON_PLAYBOOK = """
MATCH (p:Playbook {id: $pid})
CREATE (p)-[:HAS_RULE]->(:Rule {
  id: $id, kind: $kind, statement: $statement,
  node_type: $node_type, rationale: $rationale, severity: $severity})
"""

_MERGE_STAGE = """
MATCH (p:Playbook {id: $pid})
MERGE (s:Stage {id: $id})
SET s.order = $order, s.role = $role, s.purpose = $purpose,
    s.allowed_node_types = $allowed_node_types, s.key_points = $key_points
MERGE (p)-[:HAS_STAGE]->(s)
"""


def _known_node_types() -> set[str]:
    from nodes_graph.application.executable_node_types import EXECUTABLE_NODE_TYPES

    return set(EXECUTABLE_NODE_TYPES)


def load_domain_seeds(seeds_dir: Path | None = None) -> list[Domain]:
    """`seeds/domains/*.json` → 검증된 Domain VO 목록. 환각 node_type이면 ValueError."""
    directory = seeds_dir or _SEEDS_DIR
    known = _known_node_types()
    domains: list[Domain] = []
    for path in sorted(directory.glob("*.json")):
        with path.open(encoding="utf-8") as f:
            data = json.load(f)
        domains.append(parse_domain(data, known))
    return domains


async def apply_constraints(session: Any) -> None:
    for ddl in CONSTRAINTS:
        await session.run(ddl)


async def project_domains(session: Any, domains: list[Domain]) -> int:
    """도메인 서브그래프 전 재투영. 반환: 투영된 도메인 수."""
    await session.run(_RESET_DOMAINS)
    for d in domains:
        await session.run(
            _MERGE_DOMAIN, code=d.code, name=d.name, kind=d.kind, description=d.description
        )
        for i, r in enumerate(d.rules):
            await session.run(
                _CREATE_RULE_ON_DOMAIN, code=d.code, id=f"{d.code}#r{i}", kind=r.kind,
                statement=r.statement, node_type=r.node_type, rationale=r.rationale,
                severity=r.severity,
            )
        for pb in d.playbooks:
            await session.run(
                _MERGE_PLAYBOOK, code=d.code, id=pb.id, name=pb.name,
                intent=pb.intent, summary=pb.summary,
            )
            for i, r in enumerate(pb.rules):
                await session.run(
                    _CREATE_RULE_ON_PLAYBOOK, pid=pb.id, id=f"{pb.id}#r{i}", kind=r.kind,
                    statement=r.statement, node_type=r.node_type, rationale=r.rationale,
                    severity=r.severity,
                )
            for st in pb.stages:
                await session.run(
                    _MERGE_STAGE, pid=pb.id, id=f"{pb.id}#s{st.order}", order=st.order,
                    role=st.role, purpose=st.purpose,
                    allowed_node_types=list(st.allowed_node_types),
                    key_points=list(st.key_points),
                )
    return len(domains)


async def main() -> None:
    uri = os.getenv("NEO4J_URI")
    if not uri:
        raise SystemExit("NEO4J_URI 미설정 — neo4j-uri secret(또는 로컬 env) 필요 (ADR-0029)")

    from neo4j import AsyncGraphDatabase  # lazy — neo4j는 선택 의존

    domains = load_domain_seeds()
    driver = AsyncGraphDatabase.driver(
        uri, auth=(os.getenv("NEO4J_USERNAME"), os.getenv("NEO4J_PASSWORD"))
    )
    try:
        async with driver.session() as session:
            await apply_constraints(session)
            count = await project_domains(session, domains)
    finally:
        await driver.close()

    playbooks = sum(len(d.playbooks) for d in domains)
    print(f"[build_domain_ontology] 도메인 {count}건 + 플레이북 {playbooks}건 투영 완료(composer 무관)")


if __name__ == "__main__":
    asyncio.run(main())
