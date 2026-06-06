from __future__ import annotations

from dataclasses import dataclass, field

# 온톨로지 GraphRAG 검색 결과 VO (ADR-0026 Phase 1).
# 순수 도메인 — neo4j/외부 라이브러리 import 금지. 어댑터(Neo4jOntologyAdapter)가
# 그래프 질의 결과를 이 VO로 변환해 반환하고, Composer(신정혜)가 소비한다.


@dataclass(frozen=True)
class OntologyNode:
    """온톨로지가 그라운딩한 단일 노드 후보."""

    node_type: str
    category: str
    risk_level: str
    requires: tuple[str, ...] = ()  # required_connection provider 목록


@dataclass(frozen=True)
class OntologySubgraph:
    """seed node_type들을 그래프로 확장한 제약된 후보 서브그래프 (ADR-0026 §4.1).

    Phase 1: seed 노드 + 1-hop 구조 이웃(같은 category sibling). drafter가 이 집합
    **밖의** node_type을 생성하지 못하게 제약하는 데 쓴다(constrained generation =
    환각 억제). Phase 2에서 CAN_FOLLOW 호환 edge로 확장된다.
    """

    seeds: tuple[str, ...]
    nodes: tuple[OntologyNode, ...]
    # node_type → 그래프상 후행 가능 node_type (Phase 1은 category sibling, Phase 2에서
    # CAN_FOLLOW로 대체/보강). drafter 엣지 제약의 화이트리스트.
    adjacency: dict[str, tuple[str, ...]] = field(default_factory=dict)

    def allowed_node_types(self) -> frozenset[str]:
        """서브그래프가 허용하는 전체 node_type 집합 (constrained generation 가드)."""
        return frozenset(n.node_type for n in self.nodes)


@dataclass(frozen=True)
class PatternTemplate:
    """검증된 워크플로우 모티프 템플릿 (ADR-0026 §4.1, Phase 2).

    quality_gate_loop 등 control-flow 서브그래프(generator → evaluator(condition) →
    back-edge/exit-edge)를 retrieve해 drafter를 CyclicScheduler 실행가능 형태로
    grounding한다. Phase 1에서는 자리표시자 — Neo4jOntologyAdapter.match_patterns가
    Phase 2까지 NotImplementedError.
    """

    name: str
    intent: str
    # 슬롯 이름(generator/evaluator 등) → 해당 슬롯에 맞는 node_type 후보.
    role_slots: dict[str, tuple[str, ...]] = field(default_factory=dict)
