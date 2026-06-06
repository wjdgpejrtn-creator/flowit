from __future__ import annotations

from abc import ABC, abstractmethod

from ..value_objects.ontology import OntologySubgraph, PatternTemplate


class OntologyRetrieverPort(ABC):
    """온톨로지 그래프 DB(Neo4j)를 감싸는 GraphRAG 검색 포트 (ADR-0026).

    Composer(신정혜)는 Neo4j에 직접 의존하지 않고 이 인터페이스만 사용한다. 구현체
    `Neo4jOntologyAdapter`는 ai_agent가 소유한다(ADR-0013 EmbedderPort 예외 패턴 —
    Modal/외부 인프라 호출 어댑터는 호출 모듈이 보유). 구현체는 services DI에서 주입된다.

    검색 흐름(ADR-0026 §4.1): pgvector top-k로 seed node_type을 뽑은 뒤 이 포트로
    그래프 확장 → 제약된 후보 서브그래프. 벡터 검색은 pgvector 단일화 유지(Phase 1은
    Neo4j에 벡터 미복제) — 본 포트는 **구조적 확장/모티프**만 담당한다.
    """

    @abstractmethod
    async def expand_candidates(
        self, seed_node_types: list[str], hops: int = 1
    ) -> OntologySubgraph:
        """벡터 seed(node_type)들을 그래프로 확장해 제약된 후보 서브그래프를 반환한다.

        Args:
            seed_node_types: pgvector 의미검색이 1차로 뽑은 후보 node_type.
            hops: 확장 깊이. **Phase 1은 1-hop 구조 이웃(category sibling)만** 지원하며
                값은 forward-compat용 예약(Phase 2 CAN_FOLLOW 멀티홉에서 사용).
        """
        ...

    @abstractmethod
    async def match_patterns(self, intent: str) -> list[PatternTemplate]:
        """의도 문자열에 맞는 검증된 워크플로우 모티프(:Pattern) 템플릿을 반환한다.

        Phase 2 (ADR-0026 §4.1, 신정혜) — quality_gate_loop 등. Phase 1 구현체는
        NotImplementedError.
        """
        ...
