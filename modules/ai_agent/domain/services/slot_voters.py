from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from ..value_objects.skeleton import ExtractedEntities, SlotRole

# 슬롯 채움 앙상블의 voter들 (ADR-0026 §6.6 Phase 2 — 노드 선택 의미화).
#
# 배경: 순수 렉시컬(`kw in text`) 슬롯 채움은 사용자마다 다른 문법·어휘에 부서진다(§6.6.4
# e2e 누락 버그 반복 — "gmail에서 …" source 미인식 → 오선택). 신뢰할 의미신호(BGE-M3
# 리트리버는 정답 노드를 상위로 올림)가 선택 권위를 갖도록, 여러 **독립 신호**가 후보별로
# 투표하고 가중합으로 결정한다(EnsembleSlotResolver). 합의할수록 확신↑, 아무도 확신 못 하면
# 기권(조립기 폴백). 어휘 갭을 손 사전 대신 의미신호가 닫는다.
#
# 각 voter는 순수(LLM/Neo4j 직접 import 없음) — 신호는 VoteContext에 데이터로 주입돼 오프라인
# 단위테스트가 가능하다. LLM voter(방향성 디스앰비규에이션)는 async라 별도 SlotMapperPort로
# 분리(EnsembleSlotResolver가 지연 escalation).


@dataclass(frozen=True)
class VoteContext:
    """voter들에게 주입되는 신호 묶음(요청 1건 분량). 전부 순수 데이터.

    Attributes:
        utterance: 원 발화(소문자화 전/후 무관 — voter가 알아서 처리. 현재 미사용 voter도 있음).
        entities: 렉시컬 추출 결과(LexicalVoter용 — 1회 추출해 공유).
        ranked_candidates: 리트리버(BGE-M3)가 relevance 순으로 올린 후보 node_type(SemanticVoter용).
        ontology_allowed: 온톨로지 서브그래프가 허용한 node_type 집합(OntologyVoter용, 없으면 빈 집합).
    """

    utterance: str
    entities: ExtractedEntities
    ranked_candidates: tuple[str, ...] = ()
    ontology_allowed: frozenset[str] = frozenset()


@runtime_checkable
class SlotVoter(Protocol):
    """슬롯 채움 voter 계약. 역할 + 후보 풀을 받아 후보별 점수(0~1)를 낸다.

    의견 없는 후보는 dict에서 생략(= 0 기여). ``weight``는 앙상블 가중합 계수.
    """

    name: str
    weight: float

    def vote(self, ctx: VoteContext, role: SlotRole, pool: tuple[str, ...]) -> dict[str, float]:
        ...


class LexicalVoter:
    """렉시컬 추출 적중 = 1.0 (정밀·희소). 발화에 명시된 도메인 노드를 결정적으로 잡는다.

    의미신호가 못 잡는 정확 매칭("광고 시트"→google_sheets_read)을 보존 — 앙상블의 정밀 축.
    """

    name = "lexical"

    def __init__(self, weight: float = 1.0) -> None:
        self.weight = weight

    def vote(self, ctx: VoteContext, role: SlotRole, pool: tuple[str, ...]) -> dict[str, float]:
        return {nt: 1.0 for nt in ctx.entities.nodes_for_role(role) if nt in pool}


class SemanticVoter:
    """BGE-M3 의미검색 랭킹 신호 (reciprocal rank). 어휘 변형·신규 표현에 강건한 핵심 축.

    점수는 후보 **DB 거리값이 아니라 순위**로 환산(현재 거리는 정렬에만 쓰여 NodeConfig까지
    전파 안 됨 — 스키마 무변경). 역할 풀로 필터한 뒤 그 안 순위로 `1/(1+idx)`: 1등이 지배적,
    하위는 가파르게 감쇠 → 렉시컬 무음일 때 1등만 단독 바인딩 가능하게(보수적). 실코사인
    전파는 후속 정밀화.
    """

    name = "semantic"

    def __init__(self, weight: float = 0.6) -> None:
        self.weight = weight

    def vote(self, ctx: VoteContext, role: SlotRole, pool: tuple[str, ...]) -> dict[str, float]:
        pool_set = set(pool)
        ranked_in_role = [nt for nt in ctx.ranked_candidates if nt in pool_set]
        return {nt: 1.0 / (1 + idx) for idx, nt in enumerate(ranked_in_role)}


class OntologyVoter:
    """온톨로지 CAN_FOLLOW 서브그래프 멤버십 = 구조적 친화 prior (약한 tie-breaker).

    리트리버 seed를 그래프 확장한 서브그래프에 든 후보면 가점(구조적으로 워크플로우와
    연결됨). 서브그래프 미주입(Neo4j 부재/오프라인)이면 무기여로 graceful degrade — 보고된
    케이스는 lexical+semantic만으로 해소되므로 온톨로지는 가중치 낮은 보조 축. confidence
    값은 OntologySubgraph VO에 미노출이라 멤버십 이진 신호(후속에 trigger-CAN_FOLLOW 방향성으로 정밀화 가능).
    """

    name = "ontology"

    def __init__(self, weight: float = 0.25) -> None:
        self.weight = weight

    def vote(self, ctx: VoteContext, role: SlotRole, pool: tuple[str, ...]) -> dict[str, float]:
        if not ctx.ontology_allowed:
            return {}
        return {nt: 1.0 for nt in pool if nt in ctx.ontology_allowed}
