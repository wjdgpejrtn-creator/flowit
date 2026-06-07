from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any

from ...domain.ports.ontology_retriever import OntologyRetrieverPort
from ...domain.value_objects.ontology import OntologyNode, OntologySubgraph, PatternTemplate

# 확장 질의 (ADR-0026 §4.2a) — seed node_type의 자기 메타(REQUIRES) + CAN_FOLLOW 1-hop
# 순방향 이웃(후행 가능 노드). Phase 1의 category sibling 근사를 실제 CAN_FOLLOW 호환 edge로
# **교체**한다 — sibling은 "같은 범주"라 노이즈가 크고, CAN_FOLLOW는 output↔input 휴리스틱으로
# 만든 "다음에 올 수 있는 노드"라 그라운딩 정밀도가 높다(build_ontology.compute_can_follow_edges).
_EXPAND_CYPHER = """
MATCH (n:Node) WHERE n.node_type IN $seeds
OPTIONAL MATCH (n)-[:REQUIRES]->(c:Connection)
OPTIONAL MATCH (n)-[f:CAN_FOLLOW]->(succ:Node)
RETURN n.node_type AS node_type,
       n.category AS category,
       n.risk_level AS risk_level,
       collect(DISTINCT c.provider) AS requires,
       collect(DISTINCT {node_type: succ.node_type, category: succ.category,
                         risk_level: succ.risk_level, confidence: f.confidence}) AS successors
"""

# Phase 2 모티프 질의 — intent 문자열에 CONTAINS 매칭. :Pattern/USES_ROLE 시드는 박아름 §4.2.
# 데이터 없으면 빈 리스트 반환(정상 동작 — 시드 전까지 모티프 없음).
_MATCH_PATTERNS_CYPHER = """
MATCH (p:Pattern)
WHERE toLower($intent) CONTAINS toLower(p.intent)
OPTIONAL MATCH (p)-[r:USES_ROLE]->(n:Node)
WITH p, collect({slot: r.slot, node_type: n.node_type}) AS role_rows
RETURN p.name AS name,
       p.intent AS intent,
       role_rows
"""


class Neo4jOntologyAdapter(OntologyRetrieverPort):
    """OntologyRetrieverPort 구현 — Neo4j AuraDB GraphRAG 검색 (ADR-0026 Phase 1).

    **요청마다 driver 생성·close** — Composer는 Modal ASGI라 driver를 `@modal.enter`에서
    1회 생성·공유하면 asyncpg와 동일하게 boot≠request 이벤트루프 미스매치로 쿼리가
    hang한다(memory: composer_modal_per_request_engine). worker 패턴대로 호출 단위로
    엔진을 만든다.

    연결 정보는 `NEO4J_URI` / `NEO4J_USERNAME` / `NEO4J_PASSWORD` 환경변수에서 읽는다
    (하드코딩 금지). 값은 GCP secret `neo4j-uri`/`neo4j-username`/`neo4j-password`로,
    Modal `boot()`의 `load_secrets_to_env`가 런타임 주입한다(terraform 아님 — Cloud Run 전용).
    """

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
        # 테스트/DI에서 가짜 driver를 주입하기 위한 훅. None이면 실제 neo4j를 lazy import.
        self._driver_factory = driver_factory

    def _new_driver(self) -> Any:
        if self._driver_factory is not None:
            return self._driver_factory()
        # uri 검사를 neo4j import보다 먼저 — neo4j 미설치(extras 미설정) 환경에서도
        # 설정 누락이 ImportError가 아닌 명확한 RuntimeError로 드러나게 한다.
        if not self._uri:
            raise RuntimeError(
                "NEO4J_URI 미설정 — neo4j-uri secret을 load_secrets_to_env로 주입 필요 (ADR-0026)"
            )
        # neo4j는 선택 의존(extras). 모듈 import 시점에 하드 요구하지 않도록 lazy import.
        from neo4j import AsyncGraphDatabase  # noqa: PLC0415

        return AsyncGraphDatabase.driver(self._uri, auth=(self._username, self._password))

    async def expand_candidates(
        self, seed_node_types: list[str], hops: int = 1
    ) -> OntologySubgraph:
        seeds = tuple(seed_node_types)
        if not seeds:
            return OntologySubgraph(seeds=(), nodes=(), adjacency={})

        driver = self._new_driver()
        try:
            async with driver.session() as session:
                result = await session.run(_EXPAND_CYPHER, seeds=list(seeds))
                records = [record async for record in result]
        finally:
            await driver.close()

        return self._to_subgraph(seeds, records)

    async def match_patterns(self, intent: str) -> list[PatternTemplate]:
        """의도 문자열과 매칭되는 :Pattern 모티프를 반환한다 (ADR-0026 Phase 2).

        :Pattern/:USES_ROLE 시드는 박아름 §4.2 ETL 완료 전까지 빈 리스트 반환이 정상 동작.
        """
        driver = self._new_driver()
        try:
            async with driver.session() as session:
                result = await session.run(_MATCH_PATTERNS_CYPHER, intent=intent)
                records = [record async for record in result]
        finally:
            await driver.close()

        templates: list[PatternTemplate] = []
        for rec in records:
            role_rows = rec["role_rows"] or []
            role_slots: dict[str, tuple[str, ...]] = {}
            for row in role_rows:
                slot = row.get("slot")
                node_type = row.get("node_type")
                if slot and node_type:
                    role_slots.setdefault(slot, ())
                    role_slots[slot] = role_slots[slot] + (node_type,)
            templates.append(
                PatternTemplate(
                    name=rec["name"],
                    intent=rec["intent"],
                    role_slots=role_slots,
                )
            )
        return templates

    @staticmethod
    def _to_subgraph(seeds: tuple[str, ...], records: list[Any]) -> OntologySubgraph:
        nodes: dict[str, OntologyNode] = {}
        adjacency: dict[str, tuple[str, ...]] = {}
        for rec in records:
            node_type = rec["node_type"]
            requires = tuple(p for p in (rec["requires"] or []) if p)
            # CAN_FOLLOW 순방향 이웃 — null succ(이웃 없는 seed) 맵은 제외, self-loop 방지.
            # **confidence 내림차순 정렬**(동률은 node_type) — 소비측(`_expand_can_follow`) cap이
            # collect 순서(Neo4j 비보장)가 아니라 **고신뢰 이웃을 결정적으로** 보존하게 한다(#410 리뷰 MED).
            succ_rows = sorted(
                (
                    s for s in (rec["successors"] or [])
                    if s and s.get("node_type") and s["node_type"] != node_type
                ),
                key=lambda s: (-(s.get("confidence") or 0), s["node_type"]),
            )
            successors = tuple(dict.fromkeys(s["node_type"] for s in succ_rows))
            nodes[node_type] = OntologyNode(
                node_type=node_type,
                category=rec["category"],
                risk_level=rec["risk_level"],
                requires=requires,
            )
            adjacency[node_type] = successors
            # 후행 노드도 후보 집합에 포함(메타는 후속 질의 없이 그래프가 준 것만).
            for s in succ_rows:
                nodes.setdefault(
                    s["node_type"],
                    OntologyNode(
                        node_type=s["node_type"],
                        category=s.get("category") or "",
                        risk_level=s.get("risk_level") or "",
                        requires=(),
                    ),
                )

        return OntologySubgraph(
            seeds=seeds,
            nodes=tuple(nodes.values()),
            adjacency=adjacency,
        )
