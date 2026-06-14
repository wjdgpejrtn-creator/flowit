"""skill_fewshots 카테고리별 few-shot 선택 단위 테스트.

단일 환불 예시로 모든 스킬이 알림 형태로 수렴하던 편향 완화 — meta.category로 도메인 맞춤 예시 선택.
문서작성(ai/output/transform)은 Anthropic doc-coauthoring + brand-guidelines 원칙 반영.
"""
from __future__ import annotations

import re

from nodes_graph.application.executable_node_types import EXECUTABLE_NODE_TYPES

from ai_agent.application.agents.skills_builder.skill_fewshots import (
    instructions_fewshot,
    select_fewshot,
    structured_fewshot,
)


def test_document_categories_select_document_exemplar():
    for cat in ("ai", "output", "transform"):
        ex = select_fewshot(cat)
        assert ex.input_meta["node_type"] == "weekly_report_compose", cat


def test_condition_selects_branch_exemplar():
    assert select_fewshot("condition").input_meta["node_type"] == "pto_request_gate"


def test_trigger_selects_trigger_exemplar():
    assert select_fewshot("trigger").input_meta["node_type"] == "inventory_low_stock_trigger"


def test_action_and_others_select_action_exemplar():
    for cat in ("action", "integration", "utility"):
        ex = select_fewshot(cat)
        assert ex.input_meta["node_type"] == "refund_request_slack_alert", cat


def test_unknown_category_falls_back_to_action():
    assert select_fewshot("weird_unknown").input_meta["node_type"] == "refund_request_slack_alert"


def _node_refs(ex) -> set[str]:
    """exemplar composer_instructions의 백틱 토큰 중 node_type 후보 — 스킬 자신·입출력 필드는 제외."""
    non_node = (
        {ex.input_meta["node_type"]}
        | set((ex.inputs.get("properties") or {}).keys())
        | set((ex.outputs.get("properties") or {}).keys())
    )
    refs = {m.group(1) for m in re.finditer(r"`([a-z][a-z0-9_]+)`", ex.composer_instructions)}
    return {r for r in refs if "_" in r and r not in non_node}


def test_all_exemplars_composer_refs_are_real_catalog_nodes():
    # 모든 exemplar의 composer_instructions가 실제 카탈로그 node_type만 참조(환각 차단)
    for cat in ("ai", "condition", "trigger", "action"):
        ex = select_fewshot(cat)
        unknown = _node_refs(ex) - set(EXECUTABLE_NODE_TYPES)
        assert unknown == set(), f"{cat}({ex.input_meta['node_type']}) 환각 node_type: {unknown}"


def test_structured_fewshot_shape():
    eo = structured_fewshot(select_fewshot("ai"))["expected_output"]
    assert set(eo) == {"inputs", "outputs", "required_connections", "service_type", "composer_instructions"}
    assert "instructions" not in eo  # 지침서는 Call B로 분리


def test_instructions_fewshot_shape_and_nine_sections():
    fs = instructions_fewshot(select_fewshot("ai"))
    instr = fs["expected_output"]["instructions"]
    assert set(fs["expected_output"]) == {"instructions"}
    # 문서작성 exemplar도 9섹션 구조 유지
    for sec in ("## 목적", "## 처리 절차", "## 판단 규칙", "## 제약·주의"):
        assert sec in instr
    # 문서 도메인 신호(독자·요약)
    assert "독자" in instr or "요약" in instr
