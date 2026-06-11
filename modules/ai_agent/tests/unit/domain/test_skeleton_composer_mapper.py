"""SkeletonComposerMapper 단위 테스트 (ADR-0028 T5 `assemble_skill`).

AssembledDraft(순수 node_type 구조) → COMPOSER.md 본문 + 정밀 BINDS(bound_node_types) 매핑.
순수 도메인 서비스 — mock 불요. assembler 실조립 결과로도 end-to-end 매핑을 검증한다.
"""
from __future__ import annotations

from ai_agent.domain.services.skeleton_assembler import SkeletonAssembler
from ai_agent.domain.services.skeleton_composer_mapper import (
    SkeletonComposerMapper,
    SkillSkeletonMapping,
)
from ai_agent.domain.value_objects.skeleton import (
    AssembledDraft,
    DraftEdge,
    DraftNode,
    SlotRole,
)


def _linear_draft() -> AssembledDraft:
    """schedule→source→transform→sink 선형 조립(고정)."""
    nodes = (
        DraftNode(ref="trigger_0", node_type="schedule_trigger", role=SlotRole.TRIGGER),
        DraftNode(ref="source_0", node_type="google_sheets_read", role=SlotRole.SOURCE),
        DraftNode(ref="transform_0", node_type="anthropic_chat", role=SlotRole.TRANSFORM),
        DraftNode(ref="sink_0", node_type="slack_post_message", role=SlotRole.SINK),
    )
    edges = (
        DraftEdge(from_ref="trigger_0", to_ref="source_0"),
        DraftEdge(from_ref="source_0", to_ref="transform_0"),
        DraftEdge(from_ref="transform_0", to_ref="sink_0"),
    )
    return AssembledDraft(skeleton_name="scheduled_pipeline", nodes=nodes, edges=edges)


# ----------------------------------------------------------------------
# 정밀 BINDS — bound_node_types
# ----------------------------------------------------------------------


def test_bound_node_types_are_scaffold_node_types_in_order():
    mapping = SkeletonComposerMapper().map(_linear_draft())
    assert isinstance(mapping, SkillSkeletonMapping)
    assert mapping.bound_node_types == (
        "schedule_trigger",
        "google_sheets_read",
        "anthropic_chat",
        "slack_post_message",
    )


def test_bound_node_types_dedup_preserves_first_occurrence():
    # 같은 node_type이 복수 슬롯(예: 2개 sink가 동일 채널)일 때 등장 순 중복 제거
    nodes = (
        DraftNode(ref="trigger_0", node_type="manual_trigger", role=SlotRole.TRIGGER),
        DraftNode(ref="sink_0", node_type="slack_post_message", role=SlotRole.SINK),
        DraftNode(ref="sink_1", node_type="slack_post_message", role=SlotRole.SINK),
    )
    draft = AssembledDraft(skeleton_name="x", nodes=nodes, edges=())
    mapping = SkeletonComposerMapper().map(draft)
    assert mapping.bound_node_types == ("manual_trigger", "slack_post_message")


# ----------------------------------------------------------------------
# COMPOSER.md 본문
# ----------------------------------------------------------------------


def test_composer_markdown_lists_nodes_and_edges():
    md = SkeletonComposerMapper().map(_linear_draft()).composer_instructions
    assert md.startswith("## 필수 노드")
    # 스켈레톤 이름 + 모든 node_type 등장
    assert "scheduled_pipeline" in md
    for nt in ("schedule_trigger", "google_sheets_read", "anthropic_chat", "slack_post_message"):
        assert nt in md
    # 연결 섹션이 배선을 화살표로 기술
    assert "## 연결" in md
    assert "`schedule_trigger` → `google_sheets_read`" in md
    assert "`anthropic_chat` → `slack_post_message`" in md


def test_composer_markdown_annotates_branch_handles():
    # 조건 분기(true/false 핸들)는 한글 주석으로 의미를 단다
    nodes = (
        DraftNode(ref="transform_0", node_type="anthropic_chat", role=SlotRole.TRANSFORM),
        DraftNode(ref="router_0", node_type="if_condition", role=SlotRole.ROUTER),
        DraftNode(ref="sink_0", node_type="slack_post_message", role=SlotRole.SINK),
        DraftNode(ref="sink_1", node_type="gmail_send", role=SlotRole.SINK),
    )
    edges = (
        DraftEdge(from_ref="transform_0", to_ref="router_0"),
        DraftEdge(from_ref="router_0", to_ref="sink_0", from_handle="true"),
        DraftEdge(from_ref="router_0", to_ref="sink_1", from_handle="false"),
    )
    draft = AssembledDraft(skeleton_name="branch_on_classification", nodes=nodes, edges=edges)
    md = SkeletonComposerMapper().map(draft).composer_instructions
    assert "[조건 충족]" in md
    assert "[조건 미충족]" in md


def test_composer_markdown_disambiguates_duplicate_node_types_by_ref():
    nodes = (
        DraftNode(ref="trigger_0", node_type="manual_trigger", role=SlotRole.TRIGGER),
        DraftNode(ref="sink_0", node_type="slack_post_message", role=SlotRole.SINK),
        DraftNode(ref="sink_1", node_type="slack_post_message", role=SlotRole.SINK),
    )
    edges = (
        DraftEdge(from_ref="trigger_0", to_ref="sink_0"),
        DraftEdge(from_ref="trigger_0", to_ref="sink_1"),
    )
    draft = AssembledDraft(skeleton_name="x", nodes=nodes, edges=edges)
    md = SkeletonComposerMapper().map(draft).composer_instructions
    # 중복 node_type은 연결 줄에서 ref로 구분
    assert "`slack_post_message`(sink_0)" in md
    assert "`slack_post_message`(sink_1)" in md


def test_composer_markdown_surfaces_warnings():
    draft = AssembledDraft(
        skeleton_name="x",
        nodes=(DraftNode(ref="trigger_0", node_type="manual_trigger", role=SlotRole.TRIGGER),),
        edges=(),
        warnings=("required slot 'sink' 미충전 (발화에서 추출 실패)",),
    )
    md = SkeletonComposerMapper().map(draft).composer_instructions
    assert "## 주의" in md
    assert "미충전" in md
    assert "(단일 노드 — 연결 없음)" in md


# ----------------------------------------------------------------------
# end-to-end — assembler 실조립 → 매퍼
# ----------------------------------------------------------------------


def test_end_to_end_assemble_then_map():
    draft = SkeletonAssembler().assemble("매주 구글 시트 읽어서 요약해서 슬랙으로 보내줘")
    assert draft is not None  # 결정적 매칭(scheduled_pipeline)
    mapping = SkeletonComposerMapper().map(draft)
    assert mapping.skeleton_name == "scheduled_pipeline"
    # 발화의 도메인 노드가 정밀 BINDS에 결정적으로 포함
    assert "google_sheets_read" in mapping.bound_node_types
    assert "anthropic_chat" in mapping.bound_node_types
    assert "slack_post_message" in mapping.bound_node_types
    assert "schedule_trigger" in mapping.bound_node_types
