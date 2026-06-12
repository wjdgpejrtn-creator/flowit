"""DomainGroundingPort 구현 — Neo4j 도메인 서브그래프 검색 (ADR-0029). skill builder 전용.

composer의 `Neo4jOntologyAdapter`와 **완전 별개**다 — 같은 Neo4j를 쓰되 질의는
`(:Domain)/(:Playbook)/(:Stage)/(:Rule)` 라벨만 MATCH하고 composer 라벨(:Node/:Skeleton/
:Pattern)은 건드리지 않는다(서브그래프 disjoint). driver 패턴/연결 env는
`Neo4jOntologyAdapter`와 동일(요청마다 driver — Modal ASGI 이벤트루프 미스매치 회피).
"""
from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any

from ...domain.ports.domain_grounding_port import DomainGroundingPort
from ...domain.value_objects.domain_grounding import (
    Domain,
    DomainGroundingBundle,
    Playbook,
    Rule,
    Stage,
    to_bundle,
)

# 도메인 서브그래프 1쿼리 회수 — pattern comprehension으로 중첩(playbook→stage/rule) 조립.
# composer 라벨 미참조. 데이터 없으면(시드 전) MATCH 실패 → None 반환(정상 동작).
_GET_DOMAIN_CYPHER = """
MATCH (d:Domain {code: $code})
RETURN d.code AS code, d.name AS name, d.kind AS kind, d.description AS description,
  [ (d)-[:HAS_RULE]->(dr:Rule) | dr{.*} ] AS domain_rules,
  [ (d)-[:HAS_PLAYBOOK]->(p:Playbook) | p{
      .id, .name, .intent, .summary,
      rules: [ (p)-[:HAS_RULE]->(pr:Rule) | pr{.*} ],
      stages: [ (p)-[:HAS_STAGE]->(s:Stage) | s{.*} ]
  } ] AS playbooks
"""


class Neo4jDomainGroundingAdapter(DomainGroundingPort):
    """Neo4j 도메인 그라운딩 검색. 연결 정보는 `NEO4J_URI`/`NEO4J_USERNAME`/`NEO4J_PASSWORD`."""

    def __init__(
        self,
        uri: str | None = None,
        username: str | None = None,
        password: str | None = None,
        *,
        driver_factory: Callable[[], Any] | None = None,
    ) -> None:
        self._uri = uri or os.getenv("NEO4J_URI")
        self._username = username or os.getenv("NEO4J_USERNAME")
        self._password = password or os.getenv("NEO4J_PASSWORD")
        self._driver_factory = driver_factory

    def _new_driver(self) -> Any:
        if self._driver_factory is not None:
            return self._driver_factory()
        if not self._uri:
            raise RuntimeError(
                "NEO4J_URI 미설정 — neo4j-uri secret을 load_secrets_to_env로 주입 필요 (ADR-0029)"
            )
        from neo4j import AsyncGraphDatabase  # noqa: PLC0415 — neo4j는 선택 의존(lazy)

        return AsyncGraphDatabase.driver(self._uri, auth=(self._username, self._password))

    async def get_domain_grounding(self, domain_code: str) -> DomainGroundingBundle | None:
        driver = self._new_driver()
        try:
            async with driver.session() as session:
                result = await session.run(_GET_DOMAIN_CYPHER, code=domain_code)
                record = await result.single()
        finally:
            await driver.close()

        if record is None:
            return None
        return to_bundle(self._domain_from_record(record))

    @staticmethod
    def _rule_from(data: dict[str, Any]) -> Rule:
        return Rule(
            kind=data["kind"],
            statement=data.get("statement", "") or "",
            node_type=data.get("node_type"),
            rationale=data.get("rationale", "") or "",
            severity=data.get("severity", "normal") or "normal",
        )

    @classmethod
    def _stage_from(cls, data: dict[str, Any]) -> Stage:
        return Stage(
            order=int(data.get("order", 0)),
            role=data.get("role", ""),
            purpose=data.get("purpose", "") or "",
            allowed_node_types=tuple(data.get("allowed_node_types", []) or []),
            key_points=tuple(data.get("key_points", []) or []),
        )

    @classmethod
    def _playbook_from(cls, data: dict[str, Any]) -> Playbook:
        stages = tuple(sorted((cls._stage_from(s) for s in data.get("stages", [])), key=lambda s: s.order))
        return Playbook(
            id=data["id"],
            name=data.get("name", "") or "",
            intent=data.get("intent", "") or "",
            summary=data.get("summary", "") or "",
            stages=stages,
            rules=tuple(cls._rule_from(r) for r in (data.get("rules", []) or [])),
        )

    @classmethod
    def _domain_from_record(cls, rec: Any) -> Domain:
        return Domain(
            code=rec["code"],
            name=rec["name"],
            kind=rec["kind"],
            description=rec["description"] or "",
            rules=tuple(cls._rule_from(r) for r in (rec["domain_rules"] or [])),
            playbooks=tuple(cls._playbook_from(p) for p in (rec["playbooks"] or [])),
        )
