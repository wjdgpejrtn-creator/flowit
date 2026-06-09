from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

# 결정적 스켈레톤 라이브러리 VO (ADR-0026 §6.6).
#
# 배경: soft `:Pattern` 모티프 힌트(§6.1)는 작은 LLM(Gemma)의 구조 출력을 못 바꾼다고
# 양팔 라이브 측정에서 판명됐다(branch motif 0.50→0.50, robust null; PR #416). 반면 발화에
# 명시된 도메인 노드를 코드가 결정적으로 강제 포함하면 끊긴 워크플로우율 23%→0%, qa_pass
# 0.45→0.75로 개선됐다(#418). → 구조는 코드가 결정적으로 조립하고, LLM은 파라미터만 채운다.
#
# 본 VO는 그 조립의 순수 도메인 계약이다 — neo4j/외부 라이브러리 import 금지(어댑터/ETL이
# 그래프 투영을 담당). 슬롯 후보 node_type은 반드시 카탈로그에 실재하는 것만(없는 슬롯 시드
# 금지 — 환각 유발, §6.1 시드 원칙 ① 계승).


class SlotRole(str, Enum):
    """스켈레톤 슬롯 역할 (ADR-0026 §6.6.1, §6.1 role_slot 표 계승).

    데이터흐름 5역할(trigger/source/transform/sink/gate) + 제어흐름 3역할
    (router/splitter/merger). 제어 역할은 전부 condition 카테고리 노드로 채워지며 엔진의
    BranchEvaluator/CyclicScheduler 수용 계약과 정합한다. JSON 직렬화 호환 위해 ``str`` 상속.
    """

    TRIGGER = "trigger"      # 발동 — 워크플로우 진입점 (schedule/webhook/manual…)
    SOURCE = "source"        # 데이터 읽기·수집 (sheets/drive/db/http…)
    TRANSFORM = "transform"  # AI/LLM 가공 (요약·생성·분류…)
    SINK = "sink"            # 내보내는 채널 (slack/email/docs…)
    GATE = "gate"            # 생성물 검증/재시도 루프 (condition — quality_gate_loop·retry evaluator)
    ROUTER = "router"        # XOR 분기 (condition — branch/approval, if_condition/switch_case)
    SPLITTER = "splitter"    # 병렬 분할 (condition — fan_out_map, loop_list)
    MERGER = "merger"        # 병렬 합류 (condition — fan_out_map, merge_branch)
    DELAY = "delay"          # 백오프 대기 (condition — retry_backoff 재시도 경로, delay/retry)
    TERMINAL = "terminal"    # 종료 (condition — approval_gate 반려 경로, stop_workflow)


@dataclass(frozen=True)
class SlotSpec:
    """스켈레톤의 단일 슬롯 명세 (ADR-0026 §6.6.2).

    Attributes:
        role: 슬롯 역할.
        required: 슬롯이 발화 함의와 무관하게 항상 채워져야 하는지. trigger/sink는 거의
            보편 필수, source/transform/gate는 발화가 함의할 때만 활성(조건부 필수 —
            §6.6.1 "5요소 항상 필수" 정정). required 슬롯은 발화에서 못 뽑으면
            ``default_node_type``으로 채운다.
        cardinality: ``"one"``(슬롯당 노드 1개) 또는 ``"many"``(추출 엔티티 수만큼).
        default_node_type: required 슬롯이 발화에서 비었을 때 채울 기본 node_type
            (예: trigger 미지정 → manual_trigger). optional 슬롯은 ``None``.
        candidates: 이 슬롯에 들어갈 수 있는 카탈로그 node_type 후보(그래프 ``FILLED_BY``
            투영 대상). 그라운딩 가드 — 후보는 전부 실재 node_type이어야 한다.
    """

    role: SlotRole
    required: bool
    cardinality: str = "one"
    default_node_type: str | None = None
    candidates: tuple[str, ...] = ()


@dataclass(frozen=True)
class Skeleton:
    """슬롯을 가진 결정적 워크플로우 템플릿 (ADR-0026 §6.6 — `:Pattern` 확장).

    온톨로지(Neo4j)가 SSOT지만, 본 라이브러리 상수가 ETL 투영원 + 조립 소비원의 단일
    출처다(노드 카탈로그 `_PATTERNS`와 동일 패턴). 슬롯은 `order` 순서로 선형 배선되며,
    `gate` 슬롯은 직전 transform과 back-edge 루프를 이룬다(quality_gate_loop 구조).

    Attributes:
        name: 스켈레톤 식별자 (scheduled_pipeline / event_response / quality_loop).
        intent_keywords: 선택 매칭 키워드 — 발화에 CONTAINS되면 이 스켈레톤 후보.
        slots: 배선 순서대로의 슬롯 명세 튜플.
    """

    name: str
    intent_keywords: tuple[str, ...]
    slots: tuple[SlotSpec, ...]

    def slot(self, role: SlotRole) -> SlotSpec | None:
        for s in self.slots:
            if s.role == role:
                return s
        return None


@dataclass(frozen=True)
class ExtractedEntities:
    """발화에서 렉시컬/의미 추출한 슬롯 충전 재료 (ADR-0026 §6.6.3 step 1).

    각 슬롯 역할별로 node_type을 담는다. ``trigger``는 단수(진입점 1개), 나머지는 발화
    순서를 보존한 튜플. ``needs_gate``는 검증 루프 함의 여부.
    """

    trigger: str | None = None
    sources: tuple[str, ...] = ()
    transforms: tuple[str, ...] = ()
    sinks: tuple[str, ...] = ()
    needs_gate: bool = False
    # 제어흐름 shape 신호 — 조립기가 전용 스켈레톤으로 라우팅하는 근거(ADR-0026 §6.6, §9.3
    # van der Aalst ∩ agentic 모티프). 둘 이상 동시면 중첩 합성이라 flat 라이브러리로 표현
    # 불가 → 조립기가 LLM으로 bail(억지 끼워맞춤 방지). approval은 "승인되면…아니면" 구조라
    # has_branch를 동반할 수 있어 조립기가 approval을 우선(branch를 포섭)한다.
    has_branch: bool = False     # XOR 분기 — "~이면 …, 아니면 …" (Exclusive Choice / Routing)
    has_fanout: bool = False     # 병렬 팬아웃 — "각 항목마다 …" (Parallel Split / Orchestrator-Workers)
    has_retry: bool = False      # 재시도 루프 — "실패하면 재시도" (Structured Loop + delay)
    has_approval: bool = False   # 승인 게이트 — "검토 후 승인" (Deferred Choice / Human-in-the-loop)

    def is_empty(self) -> bool:
        """트리거 외에 아무 슬롯 재료도 없으면 True(조립 무의미 — fast-path/폴백 판단용)."""
        return not (self.sources or self.transforms or self.sinks or self.needs_gate)

    def shape_signals(self) -> set[str]:
        """감지된 제어흐름 shape 신호 집합 (조립기 라우팅·중첩 판정용)."""
        return {
            name
            for name, flag in (
                ("approval", self.has_approval),
                ("retry", self.has_retry),
                ("fanout", self.has_fanout),
                ("branch", self.has_branch),
            )
            if flag
        }


@dataclass(frozen=True)
class DraftNode:
    """조립된 워크플로우의 노드 1개 (node_id 미해소 — 순수 node_type 수준)."""

    ref: str          # 조립 내 안정 식별자 (엣지 참조용, 중복 node_type 허용)
    node_type: str
    role: SlotRole


@dataclass(frozen=True)
class DraftEdge:
    """조립된 워크플로우의 엣지 1개 (ref 기반 — drafter `_EditEdgeDraft`와 동형)."""

    from_ref: str
    to_ref: str
    from_handle: str = "output"
    to_handle: str = "input"


@dataclass(frozen=True)
class AssembledDraft:
    """스켈레톤 조립 결과 (ADR-0026 §6.6.3 step 4) — 코드가 결정한 구조.

    node_id/instance_id 미해소(순수). composer가 카탈로그 node_id로 해소해
    WorkflowSchema로 변환하고(`to_workflow_schema`), LLM은 파라미터만 채운다(step 5).
    """

    skeleton_name: str
    nodes: tuple[DraftNode, ...] = ()
    edges: tuple[DraftEdge, ...] = ()
    # 채우지 못한 required 슬롯 등 조립 경고(폴백/관측용). 비면 완전 조립.
    warnings: tuple[str, ...] = field(default_factory=tuple)
