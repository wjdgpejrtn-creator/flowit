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


def test_sink_missing_bails_to_llm() -> None:
    # sink(출력 채널)를 발화에서 못 채우면 토막 골격 대신 LLM 폴백(불완전 커버리지 게이트).
    assert _A.assemble("매주 시트 읽어서 요약") is None


def test_branch_request_bails_to_llm() -> None:
    # XOR 분기는 현 라이브러리가 결정적으로 못 짬 → 선형 납작화 대신 LLM 폴백.
    assert _A.assemble("문의가 들어오면 분류해서 긴급하면 슬랙, 아니면 이메일로 보내줘") is None


def test_fanout_request_bails_to_llm() -> None:
    # 병렬 팬아웃도 미지원 shape → LLM 폴백.
    assert _A.assemble("목록의 각 항목마다 요약해서 슬랙으로 보내줘") is None


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
    "웹훅 들어오면 내용 분석해서 이메일로 보내줘",
    "보고서 초안 생성하고 품질 기준 통과할 때까지 재생성한 다음 구글 docs에 저장",
    "매주 보고서 생성하고 기준 충족할 때까지 검증해서 슬랙 알림",
    "빅쿼리 조회해서 요약하고 pdf로 저장",
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
