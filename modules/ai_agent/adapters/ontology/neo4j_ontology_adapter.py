from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any

from ...domain.ports.ontology_retriever import OntologyRetrieverPort
from ...domain.value_objects.ontology import OntologyNode, OntologySubgraph, PatternTemplate

# Phase 1 확장 질의 — seed node_type의 자기 메타(REQUIRES) + 같은 category sibling 1-hop.
# CAN_FOLLOW 호환 edge(Phase 2)는 아직 없으므로 구조 이웃은 category 공유로 근사한다.
_EXPAND_CYPHER = """
MATCH (n:Node) WHERE n.node_type IN $seeds
OPTIONAL MATCH (n)-[:REQUIRES]->(c:Connection)
OPTIONAL MATCH (n)-[:IN_CATEGORY]->(:Category)<-[:IN_CATEGORY]-(sib:Node)
RETURN n.node_type AS node_type,
       n.category AS category,
       n.risk_level AS risk_level,
       collect(DISTINCT c.provider) AS requires,
       collect(DISTINCT sib.node_type) AS siblings
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
        raise NotImplementedError(
            "Phase 2 — :Pattern 모티프 retrieval (신정혜, ADR-0026 §4.1)"
        )

    @staticmethod
    def _to_subgraph(seeds: tuple[str, ...], records: list[Any]) -> OntologySubgraph:
        nodes: dict[str, OntologyNode] = {}
        adjacency: dict[str, tuple[str, ...]] = {}
        for rec in records:
            node_type = rec["node_type"]
            requires = tuple(p for p in (rec["requires"] or []) if p)
            siblings = tuple(s for s in (rec["siblings"] or []) if s and s != node_type)
            nodes[node_type] = OntologyNode(
                node_type=node_type,
                category=rec["category"],
                risk_level=rec["risk_level"],
                requires=requires,
            )
            adjacency[node_type] = siblings
            # category sibling도 후보 노드 집합에 포함(메타는 후속 질의 없이 최소만).
            for sib in siblings:
                nodes.setdefault(
                    sib, OntologyNode(node_type=sib, category=rec["category"], risk_level="", requires=())
                )

        return OntologySubgraph(
            seeds=seeds,
            nodes=tuple(nodes.values()),
            adjacency=adjacency,
        )
