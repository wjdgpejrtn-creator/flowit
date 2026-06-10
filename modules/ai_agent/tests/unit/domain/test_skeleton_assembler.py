"""결정적 조립기 + 엔진 계약 파리티 테스트 (ADR-0026 §6.6.3 / §6.6.5).

조립기는 발화를 결정적 골격으로 짜고(구조 단위테스트), 조립 골격이 GraphValidator(=#392
CyclicScheduler 1:1 정합)의 **구조 검증을 통과**함을 파리티로 보장한다 — composer가 통과시킨
스켈레톤 draft가 엔진에서 죽는 false accept를 차단(§6.6.5).
"""
from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from common_schemas.enums import ErrorCode
from nodes_graph.application.catalog_registry import get_all_node_definitions
from nodes_graph.domain.services.graph_validator import GraphValidator

from ai_agent.domain.services.skeleton_assembler import SkeletonAssembler, to_workflow_schema
from ai_agent.domain.value_objects.skeleton import SlotRole

_A = SkeletonAssembler()

_DEFS = get_all_node_definitions()
_NODE_ID_BY_TYPE: dict[str, UUID] = {d.node_type: d.node_id for d in _DEFS}
_DEF_BY_ID = {d.node_id: d for d in _DEFS}

# 조립 골격에서 다운스트림(파라미터/자격증명 바인딩)이 채울 에러는 파리티 범위 밖. 스켈레톤이
# 보장하는 건 **구조** 무결성뿐(LLM이 파라미터, autobind이 connection을 채움 — §6.6.3 step 5).
_STRUCTURAL_CODES = {
    ErrorCode.E_DUPLICATE_ID,
    ErrorCode.E_CYCLE_DETECTED,
    ErrorCode.E_ISOLATED_NODE,
}


class _CatalogRepo:
    """GraphValidator용 인메모리 NodeDefinitionRepository (get_by_id만 사용)."""

    async def get_by_id(self, node_id: UUID):  # noqa: ANN201 - 도메인 NodeDefinition 반환
        return _DEF_BY_ID.get(node_id)


def _node_types(draft) -> list[str]:
    return [n.node_type for n in draft.nodes]


# ── 구조 조립 ──────────────────────────────────────────────────────────────
def test_scheduled_pipeline_e2e_bug_golden() -> None:
    # §6.6.4 e2e 버그 직격: "광고 시트"가 결정적으로 source 슬롯을 채워 google_sheets_read
    # 강제 진입 → 4노드 선형(schedule→sheets→ai→slack). 의미검색 랭킹 의존 0.
    d = _A.assemble("매주 월요일에 광고 시트 읽어서 요약해서 슬랙으로 보내줘")
    assert d is not None
    assert d.skeleton_name == "scheduled_pipeline"
    assert _node_types(d) == [
        "schedule_trigger", "google_sheets_read", "anthropic_chat", "slack_post_message",
    ]
    assert d.warnings == ()
    # 선형 배선 — 연속 3엣지, back-edge 없음.
    assert len(d.edges) == 3
    assert all(e.from_handle == "output" for e in d.edges)


def test_event_response_skeleton() -> None:
    d = _A.assemble("웹훅 들어오면 내용 분석해서 이메일로 보내줘")
    assert d is not None
    assert d.skeleton_name == "event_response"
    assert _node_types(d) == ["webhook_trigger", "anthropic_chat", "email_send"]


def test_quality_loop_has_back_edge_and_exit() -> None:
    d = _A.assemble("보고서 초안 생성하고 품질 기준 통과할 때까지 재생성한 다음 구글 docs에 저장")
    assert d is not None
    assert d.skeleton_name == "quality_loop"
    gate = next(n for n in d.nodes if n.role == SlotRole.GATE)
    gen = next(n for n in d.nodes if n.role == SlotRole.TRANSFORM)
    sink = next(n for n in d.nodes if n.role == SlotRole.SINK)
    # back-edge(false→generator) + exit(true→sink) 둘 다 존재.
    assert any(e.from_ref == gate.ref and e.to_ref == gen.ref and e.from_handle == "false"
               for e in d.edges)
    assert any(e.from_ref == gate.ref and e.to_ref == sink.ref and e.from_handle == "true"
               for e in d.edges)


def test_quality_loop_inserts_scorer_between_generator_and_gate() -> None:
    # #438 §6.6: generator(ai)→scorer(llm_judge, 점수화)→gate(if_condition, gte 비교). gate가
    # 비교할 score를 scorer가 낸다. back-edge는 generator로(재생성), scorer 경유 아님.
    d = _A.assemble("보고서 초안 생성하고 품질 기준 통과할 때까지 재생성한 다음 구글 docs에 저장")
    assert d is not None
    scorer = next(n for n in d.nodes if n.role == SlotRole.SCORER)
    gen = next(n for n in d.nodes if n.role == SlotRole.TRANSFORM)
    gate = next(n for n in d.nodes if n.role == SlotRole.GATE)
    assert scorer.node_type == "llm_judge"
    # generator → scorer → gate 직렬, gate에 직접 들어오는 건 scorer뿐(generator 아님).
    assert any(e.from_ref == gen.ref and e.to_ref == scorer.ref for e in d.edges)
    assert any(e.from_ref == scorer.ref and e.to_ref == gate.ref for e in d.edges)
    assert not any(e.from_ref == gen.ref and e.to_ref == gate.ref for e in d.edges)
    # scorer는 루프 안(back-edge 대상 아님) — gate의 false는 generator로만 되돌아간다.
    assert not any(e.to_ref == scorer.ref and e.from_handle == "false" for e in d.edges)


def test_needs_gate_routes_to_quality_loop_over_schedule() -> None:
    # 스케줄 키워드 + 검증 함의가 함께면 needs_gate가 quality_loop로 라우팅(gate 불변 보장).
    d = _A.assemble("매주 보고서 생성하고 기준 충족할 때까지 검증")
    assert d is not None
    assert d.skeleton_name == "quality_loop"
    assert any(n.node_type == "schedule_trigger" for n in d.nodes)  # 트리거는 발화 존중


def test_trigger_default_when_unspecified() -> None:
    d = _A.assemble("시트 읽어서 슬랙으로 보내줘")
    assert d is not None
    assert d.nodes[0].node_type == "schedule_trigger"  # scheduled_pipeline default


def test_chitchat_returns_none() -> None:
    assert _A.assemble("안녕 오늘 날씨 어때") is None


def test_content_without_sink_gets_default_doc_output() -> None:
    # 콘텐츠 생산(요약=transform) 있는데 출력 채널 미언급 → 기본 문서 출력(google_docs_write) 부여
    # — 산출물이 갈 곳 없는 워크플로우를 qa가 불완전 저평가하는 것 방지(2026-06-09 측정 (b)).
    d = _A.assemble("매주 시트 읽어서 요약")
    assert d is not None
    assert d.skeleton_name == "scheduled_pipeline"
    assert _node_types(d) == [
        "schedule_trigger", "google_sheets_read", "anthropic_chat", "google_docs_write",
    ]


def test_source_only_no_default_sink() -> None:
    # transform 없는 read-only(시트만 읽기)는 기본 문서 출력 강제 안 함 — 종단 유지.
    d = _A.assemble("매주 시트 읽어줘")
    assert d is not None
    assert not any(n.node_type == "google_docs_write" for n in d.nodes)


def test_terse_sink_only_request_bails() -> None:
    # RC1(skeleton-regressor-fix): source/transform 없는 sink-only 발화는 스켈레톤이 trigger+sink
    # 토막만 만들어 LLM 자유조립보다 못하다(측정: lin_make_doc 스켈레톤 8.7 < LLM 10). #440의
    # terse-doc 결정적 진입을 의도적으로 좁혀 None(LLM 폴백) 반환.
    d = _A.assemble("보고서 문서 하나 만들어줘")
    assert d is None


def test_terse_quality_loop_assembles() -> None:
    # "검수/통과 못 하면" gate 보강 — quality_loop 발동(이전엔 gate 미감지→None).
    d = _A.assemble("영어 번역문을 만들고 검수해서 통과 못 하면 다시 번역 반복해줘")
    assert d is not None
    assert d.skeleton_name == "quality_loop"
    assert "if_condition" in [n.node_type for n in d.nodes]


def test_empty_still_bails() -> None:
    # sink optional이어도 트리거뿐(의미 재료 전무)이면 여전히 None(is_empty 가드 유지).
    assert _A.assemble("안녕 오늘 날씨 좋네") is None


# ── 분기 (XOR) ─────────────────────────────────────────────────────────────
def test_branch_assembles_xor_to_two_sinks() -> None:
    # classifier(ai)→router(if_condition)→ true/false 2갈래 sink. 핸들=BranchEvaluator selector.
    d = _A.assemble("문의를 분류해서 긴급하면 슬랙, 아니면 이메일로 보내줘")
    assert d is not None
    assert d.skeleton_name == "branch_on_classification"
    router = next(n for n in d.nodes if n.role == SlotRole.ROUTER)
    assert router.node_type == "if_condition"
    classifier = next(n for n in d.nodes if n.role == SlotRole.TRANSFORM)
    sinks = [n for n in d.nodes if n.role == SlotRole.SINK]
    assert len(sinks) == 2
    assert any(e.from_ref == classifier.ref and e.to_ref == router.ref for e in d.edges)
    handles = {e.from_handle for e in d.edges if e.from_ref == router.ref}
    assert handles == {"true", "false"}


def test_branch_with_three_sinks_bails_to_llm() -> None:
    # 3갈래↑는 if_condition 2-way로 표현 불가(switch_case 다중은 정적 모호) → LLM 폴백.
    assert _A.assemble("조건에 따라 긴급은 슬랙, 보통은 이메일, 낮으면 linear 이슈로") is None


# ── 팬아웃 (병렬 map) ───────────────────────────────────────────────────────
def test_fanout_assembles_split_worker_merge() -> None:
    d = _A.assemble("목록의 각 항목마다 요약해서 슬랙으로 보내줘")
    assert d is not None
    assert d.skeleton_name == "fan_out_map"
    types = [n.node_type for n in d.nodes]
    assert "loop_list" in types and "merge_branch" in types
    splitter = next(n for n in d.nodes if n.role == SlotRole.SPLITTER)
    worker = next(n for n in d.nodes if n.role == SlotRole.TRANSFORM)
    merger = next(n for n in d.nodes if n.role == SlotRole.MERGER)
    # splitter→worker→merger 연쇄.
    assert any(e.from_ref == splitter.ref and e.to_ref == worker.ref for e in d.edges)
    assert any(e.from_ref == worker.ref and e.to_ref == merger.ref for e in d.edges)


def test_fanout_without_sink_bails_to_llm() -> None:
    assert _A.assemble("각 항목마다 요약해줘") is None


def test_nested_branch_in_fanout_bails_to_llm() -> None:
    # 중첩 합성(팬아웃 안 분기)은 flat 라이브러리로 표현 불가 → LLM 폴백(§6.6 측정 게이트).
    assert _A.assemble("각 항목마다 분류해서 긴급하면 슬랙, 아니면 이메일") is None


# ── 재시도 (백오프 루프) ────────────────────────────────────────────────────
def test_retry_assembles_backoff_loop() -> None:
    d = _A.assemble("외부 api 호출해서 실패하면 재시도하고 결과를 슬랙으로")
    assert d is not None
    assert d.skeleton_name == "retry_backoff"
    types = [n.node_type for n in d.nodes]
    assert "delay" in types and "if_condition" in types
    gate = next(n for n in d.nodes if n.role == SlotRole.GATE)
    delay = next(n for n in d.nodes if n.role == SlotRole.DELAY)
    worker = next(n for n in d.nodes if n.node_type == "http_request")
    # 실패(false)→delay→worker 백오프 루프 + 성공(true)→sink.
    assert any(e.from_ref == gate.ref and e.to_ref == delay.ref and e.from_handle == "false"
               for e in d.edges)
    assert any(e.from_ref == delay.ref and e.to_ref == worker.ref for e in d.edges)
    assert any(e.from_ref == gate.ref and e.from_handle == "true" for e in d.edges)


def test_retry_without_operation_bails_to_llm() -> None:
    # 재시도할 연산(source/transform)이 발화에 없으면 LLM 폴백.
    assert _A.assemble("실패하면 재시도") is None


# ── 승인 게이트 (HITL) ──────────────────────────────────────────────────────
def test_approval_assembles_router_with_stop() -> None:
    d = _A.assemble("보고서 초안 작성하고 검토 후 승인되면 이메일로 발송")
    assert d is not None
    assert d.skeleton_name == "approval_gate"
    types = [n.node_type for n in d.nodes]
    assert "if_condition" in types and "stop_workflow" in types
    router = next(n for n in d.nodes if n.role == SlotRole.ROUTER)
    terminal = next(n for n in d.nodes if n.role == SlotRole.TERMINAL)
    sink = next(n for n in d.nodes if n.role == SlotRole.SINK)
    assert any(e.from_ref == router.ref and e.to_ref == terminal.ref and e.from_handle == "false"
               for e in d.edges)
    assert any(e.from_ref == router.ref and e.to_ref == sink.ref and e.from_handle == "true"
               for e in d.edges)


def test_approval_subsumes_branch_signal() -> None:
    # "승인되면 …, 아니면 …"은 approval+branch 동시 신호지만 approval로 라우팅(branch 포섭).
    d = _A.assemble("초안 검토 후 승인되면 슬랙으로 발송, 아니면 중단")
    assert d is not None
    assert d.skeleton_name == "approval_gate"


def test_conditional_guard_assembles_router_with_stop() -> None:
    # 단일 가드("임계치 넘으면 경보") — conditional_action: router(if_condition)→true→sink/
    # false→stop_workflow. transform 없음(가드는 분류기 불필요). RC2 — 폴백으로 if_condition
    # 소실되던 branch_threshold_alert 회귀 직격.
    d = _A.assemble("온도 값이 임계치를 넘으면 경보 메일을 보내줘")
    assert d is not None
    assert d.skeleton_name == "conditional_action"
    types = [n.node_type for n in d.nodes]
    assert "if_condition" in types and "stop_workflow" in types
    assert not any(n.role == SlotRole.TRANSFORM for n in d.nodes)  # 가드=분류기 없음
    router = next(n for n in d.nodes if n.role == SlotRole.ROUTER)
    terminal = next(n for n in d.nodes if n.role == SlotRole.TERMINAL)
    sink = next(n for n in d.nodes if n.role == SlotRole.SINK)
    assert any(e.from_ref == router.ref and e.to_ref == terminal.ref and e.from_handle == "false"
               for e in d.edges)
    assert any(e.from_ref == router.ref and e.to_ref == sink.ref and e.from_handle == "true"
               for e in d.edges)
    # router outgoing ≥2 (true sink + false terminal) → motif(branch_on_classification) 정합.
    out = [e for e in d.edges if e.from_ref == router.ref]
    assert len(out) >= 2


def test_conditional_guard_with_classifier_keeps_transform() -> None:
    # 분류 가드("분류해서 …넘으면")는 transform(분류기)도 동반 — spine에 포함.
    d = _A.assemble("점수를 분석해서 80점을 넘으면 슬랙으로 알림 보내줘")
    assert d is not None
    assert d.skeleton_name == "conditional_action"
    assert any(n.role == SlotRole.TRANSFORM for n in d.nodes)


def test_branch_signal_wins_over_guard() -> None:
    # guard("넘으면")+branch("아니면") 동반 + 2 sink → branch_on_classification(분기 우선, guard
    # 양보). assemble의 `shapes.discard("guard")` 우선순위(approval>branch>guard) 회귀 가드.
    d = _A.assemble("금액이 100만원을 넘으면 슬랙으로 알림, 아니면 이메일로 보내줘")
    assert d is not None
    assert d.skeleton_name == "branch_on_classification"


def test_approval_wins_over_guard() -> None:
    # approval("승인")+guard("넘으면") 동반 → approval_gate(승인 우선, guard 양보).
    d = _A.assemble("금액이 한도를 넘으면 검토 후 승인되면 이메일로 발송")
    assert d is not None
    assert d.skeleton_name == "approval_gate"


def test_guard_without_sink_bails_to_llm() -> None:
    # 가드 신호여도 action 채널(sink) 못 채우면 LLM 폴백(억지 조립 금지).
    assert _A.assemble("값이 임계치를 넘으면 처리해줘") is None


def test_terse_sink_only_does_not_force_pipeline() -> None:
    # RC1: source/transform 없는 sink-only는 None(LLM). (test_terse_sink_only_request_bails 보강 —
    # 다양한 sink 채널에서 일관)
    assert _A.assemble("슬랙으로 공지 하나 보내줘") is None


def test_transform_only_no_sink_bails() -> None:
    # RC1: 출력 채널(sink) 없는 transform-only는 catch-all 미발동 → None(LLM). default 문서 sink
    # 오주입(google_docs_write) 방지 — 측정상 LLM 자유조립이 나음(lin_fetch_summarize).
    assert _A.assemble("이 URL 내용을 가져와서 요약해줘") is None


def test_real_pipeline_with_sink_still_assembles() -> None:
    # source/transform + sink 갖춘 실제 파이프라인은 catch-all로 정상 조립(승리 케이스 보존).
    d = _A.assemble("구글시트 데이터를 읽어서 요약 메일로 보내줘")
    assert d is not None
    assert d.skeleton_name == "scheduled_pipeline"
    types = [n.node_type for n in d.nodes]
    assert "google_sheets_read" in types and "email_send" in types


def test_multiple_sinks_fan_out_in_parallel() -> None:
    # 복수 sink는 직렬(sink→sink)이 아니라 마지막 처리 노드에서 병렬 분기.
    d = _A.assemble("매주 시트 읽어서 요약해서 슬랙이랑 이메일 둘 다 보내줘")
    assert d is not None
    transform = next(n for n in d.nodes if n.role == SlotRole.TRANSFORM)
    sinks = [n for n in d.nodes if n.role == SlotRole.SINK]
    assert len(sinks) == 2
    # 두 sink 모두 transform에서 직접 나오고, sink끼리 잇는 엣지는 없다.
    for s in sinks:
        assert any(e.from_ref == transform.ref and e.to_ref == s.ref for e in d.edges)
    sink_refs = {s.ref for s in sinks}
    assert not any(e.from_ref in sink_refs and e.to_ref in sink_refs for e in d.edges)


# ── 의미검색 후보 그라운딩 (#453, ADR-0026 §6.6) ─────────────────────────────
# 렉시컬이 비운 source/sink 슬롯을 retriever 후보(BGE-M3 의미매칭, rank 순)로 채운다 —
# 어휘 갭(스펠링 변형·신규 표현)을 손 사전 대신 의미검색 결과로 닫는다.
def test_saream2_full_chain_with_calc_keyword() -> None:
    # #453 블로커 직격: "전주 대비 증감 계산 → 정산 구글독스" 4노드 풀체인. "계산"이 transform
    # (AI)을 켜고, transform 종단에 default 문서 sink가 붙어 schedule→sheets→ai→docs 완성.
    d = _A.assemble(
        "매주 월요일 아침에 구글 '주간매출' 시트 읽어서 전주 대비 증감 계산해서 정산 구글독스로 써줘"
    )
    assert d is not None
    assert d.skeleton_name == "scheduled_pipeline"
    assert _node_types(d) == [
        "schedule_trigger", "google_sheets_read", "anthropic_chat", "google_docs_write",
    ]


def test_candidate_grounding_fills_lexically_missed_sink() -> None:
    # transform 없음(default-docs-sink 마스킹 배제) + sink "구글독스" 렉시컬 미매칭 →
    # 그라운딩 없으면 2노드(토막), 후보에 google_docs_write 있으면 3노드로 채움.
    intent = "매주 시트 데이터를 구글독스로 옮겨줘"
    assert _node_types(_A.assemble(intent)) == ["schedule_trigger", "google_sheets_read"]
    grounded = _A.assemble(
        intent, candidate_node_types=["google_sheets_read", "google_docs_write", "anthropic_chat"]
    )
    assert _node_types(grounded) == [
        "schedule_trigger", "google_sheets_read", "google_docs_write",
    ]


def test_grounding_does_not_override_lexical_sink() -> None:
    # 렉시컬이 이미 sink("슬랙")를 채우면 후보에 다른 sink가 있어도 안 건드린다(정밀 보존·over-add 0).
    d = _A.assemble(
        "매주 시트 읽어서 요약해서 슬랙으로 보내줘",
        candidate_node_types=["google_sheets_read", "google_docs_write", "email_send", "anthropic_chat"],
    )
    assert _node_types(d) == [
        "schedule_trigger", "google_sheets_read", "anthropic_chat", "slack_post_message",
    ]


def test_grounding_excludes_transform_slot() -> None:
    # transform 후보(anthropic_chat)는 retriever가 항상 후보에 넣어(#418) 비변별적 → 그라운딩
    # 제외. transform 의도어("계산/요약") 없는 발화엔 후보에 anthropic_chat이 있어도 AI 노드를
    # 끼우지 않는다(over-add 방지).
    d = _A.assemble(
        "매주 시트 데이터를 구글독스로 옮겨줘",
        candidate_node_types=["google_sheets_read", "google_docs_write", "anthropic_chat", "gemma_chat"],
    )
    assert "anthropic_chat" not in _node_types(d) and "gemma_chat" not in _node_types(d)


def test_grounding_absent_preserves_legacy_behavior() -> None:
    # candidate_node_types 미전달(=None) → 순수 렉시컬(기존 동작). 기존 호출처·테스트 호환.
    base = _A.assemble("매주 광고 시트 읽어서 요약해서 슬랙으로 보내줘")
    with_none = _A.assemble("매주 광고 시트 읽어서 요약해서 슬랙으로 보내줘", candidate_node_types=None)
    assert _node_types(base) == _node_types(with_none)


# ── 변환기 ─────────────────────────────────────────────────────────────────
def test_to_workflow_schema_maps_node_ids_and_edges() -> None:
    d = _A.assemble("매주 광고 시트 읽어서 요약해서 슬랙으로 보내줘")
    assert d is not None
    owner = uuid4()
    wf = to_workflow_schema(d, _NODE_ID_BY_TYPE, owner)
    assert len(wf.nodes) == len(d.nodes)
    assert len(wf.connections) == len(d.edges)
    assert wf.owner_user_id == owner
    assert all(n.node_id in _DEF_BY_ID for n in wf.nodes)
    assert len({n.instance_id for n in wf.nodes}) == len(wf.nodes)  # instance_id 유일


# ── 엔진 계약 파리티 ────────────────────────────────────────────────────────
_PARITY_UTTERANCES = [
    "매주 월요일에 광고 시트 읽어서 요약해서 슬랙으로 보내줘",
    "매주 월요일 아침에 구글 '주간매출' 시트 읽어서 전주 대비 증감 계산해서 정산 구글독스로 써줘",  # #453

    "웹훅 들어오면 내용 분석해서 이메일로 보내줘",
    "보고서 초안 생성하고 품질 기준 통과할 때까지 재생성한 다음 구글 docs에 저장",
    "매주 보고서 생성하고 기준 충족할 때까지 검증해서 슬랙 알림",
    "빅쿼리 조회해서 요약하고 pdf로 저장",
    "문의를 분류해서 긴급하면 슬랙, 아니면 이메일로 보내줘",          # 분기(XOR)
    "목록의 각 항목마다 요약해서 슬랙으로 보내줘",                      # 팬아웃(병렬 map)
    "외부 api 호출해서 실패하면 재시도하고 결과를 슬랙으로",            # 재시도(백오프 루프)
    "보고서 초안 작성하고 검토 후 승인되면 이메일로 발송",              # 승인 게이트(HITL)
    "온도 값이 임계치를 넘으면 경보 메일을 보내줘",                    # 단일 가드(conditional_action)
]


@pytest.mark.asyncio
@pytest.mark.parametrize("utterance", _PARITY_UTTERANCES)
async def test_assembled_workflow_passes_structural_validation(utterance: str) -> None:
    d = _A.assemble(utterance)
    assert d is not None
    wf = to_workflow_schema(d, _NODE_ID_BY_TYPE, uuid4())
    result = await GraphValidator(_CatalogRepo()).validate(wf)
    structural = [e for e in result.errors if e.code in _STRUCTURAL_CODES]
    assert not structural, f"구조 검증 실패({utterance}): {[(e.code, e.message) for e in structural]}"


@pytest.mark.asyncio
async def test_quality_loop_cycle_accepted_by_validator() -> None:
    # gate(condition) 포함 SCC라 #392 validator(SCC당 condition≥1)가 수용 — 무한루프 false accept 아님.
    d = _A.assemble("초안 생성하고 품질 통과할 때까지 재생성")
    assert d is not None
    wf = to_workflow_schema(d, _NODE_ID_BY_TYPE, uuid4())
    result = await GraphValidator(_CatalogRepo()).validate(wf)
    assert not [e for e in result.errors if e.code == ErrorCode.E_CYCLE_DETECTED]
