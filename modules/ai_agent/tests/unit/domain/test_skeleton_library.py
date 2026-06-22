"""스켈레톤 라이브러리 그라운딩 가드 (ADR-0026 §6.6 시드 원칙 ①).

슬롯 후보·default node_type이 전부 카탈로그(54종)에 실재하는지 카탈로그 대조로 강제한다.
없는 node_type을 시드하면 조립기가 환각 노드를 생성하므로(§6.1 원칙 계승) 회귀 차단.
"""
from __future__ import annotations

import pytest
from nodes_graph.application.catalog_registry import get_all_node_definitions

from ai_agent.domain.services.skeleton_library import SKELETONS, find_skeleton
from ai_agent.domain.value_objects.skeleton import SlotRole

_CATALOG = frozenset(d.node_type for d in get_all_node_definitions())


def test_all_slot_candidates_exist_in_catalog() -> None:
    for skel in SKELETONS:
        for slot in skel.slots:
            for nt in slot.candidates:
                assert nt in _CATALOG, f"{skel.name}/{slot.role.value}: 미존재 후보 {nt}"


def test_all_defaults_exist_and_are_own_candidate() -> None:
    for skel in SKELETONS:
        for slot in skel.slots:
            if slot.default_node_type is None:
                continue
            assert slot.default_node_type in _CATALOG
            assert slot.default_node_type in slot.candidates, (
                f"{skel.name}/{slot.role.value}: default가 candidates에 없음"
            )


def test_required_slots_have_default() -> None:
    # required 슬롯은 발화에서 못 뽑아도 채울 수 있어야(폴백). sink만 예외(채널은 발화 의존).
    for skel in SKELETONS:
        for slot in skel.slots:
            if slot.required and slot.role != SlotRole.SINK:
                assert slot.default_node_type is not None, (
                    f"{skel.name}/{slot.role.value}: required인데 default 없음"
                )


def test_skeletons_have_intent_keywords_and_unique_names() -> None:
    names = [s.name for s in SKELETONS]
    assert len(names) == len(set(names))
    for skel in SKELETONS:
        assert skel.intent_keywords, f"{skel.name}: intent_keywords 비어있음"


def test_quality_loop_has_generator_scorer_and_gate() -> None:
    # quality_gate_loop의 결정적 부활 — transform(generator)+scorer(채점)+gate(evaluator)
    # 셋 다 required. scorer(#438 §6.6)가 gate가 비교할 score를 낸다.
    skel = find_skeleton("quality_loop")
    assert skel is not None
    transform = skel.slot(SlotRole.TRANSFORM)
    scorer = skel.slot(SlotRole.SCORER)
    gate = skel.slot(SlotRole.GATE)
    assert transform is not None and transform.required
    assert scorer is not None and scorer.required
    assert scorer.default_node_type == "llm_judge"
    assert scorer.candidates == ("llm_judge",)
    assert gate is not None and gate.required


def test_control_role_candidates_are_condition_nodes() -> None:
    # control 슬롯(gate/router/splitter/merger) 후보는 전부 condition 노드여야 — 엔진의
    # BranchEvaluator/CyclicScheduler가 분기·루프·합류를 condition 카테고리로 해석.
    cond = {d.node_type for d in get_all_node_definitions() if d.category == "condition"}
    control_roles = (
        SlotRole.GATE, SlotRole.ROUTER, SlotRole.SPLITTER, SlotRole.MERGER,
        SlotRole.DELAY, SlotRole.TERMINAL,
    )
    for skel in SKELETONS:
        for role in control_roles:
            slot = skel.slot(role)
            if slot is None:
                continue
            for nt in slot.candidates:
                assert nt in cond, f"{skel.name}/{role.value}: 후보 {nt}가 condition 노드 아님"


def test_branch_and_fanout_have_required_control_slots() -> None:
    branch = find_skeleton("branch_on_classification")
    assert branch is not None
    assert branch.slot(SlotRole.ROUTER) is not None and branch.slot(SlotRole.ROUTER).required
    fanout = find_skeleton("fan_out_map")
    assert fanout is not None
    # splitter/worker는 fanout 구조의 필수. merger는 **optional** — 단일채널 per-item 루프엔
    # 합류가 불필요하고, required로 강제하면 merge_branch(branches required)가 무조건 삽입돼
    # 검증 실패하던 회귀 때문(조장 e2e). 합류는 발화/앙상블이 명시할 때만.
    for role in (SlotRole.SPLITTER, SlotRole.TRANSFORM):
        slot = fanout.slot(role)
        assert slot is not None and slot.required
    merger = fanout.slot(SlotRole.MERGER)
    assert merger is not None and not merger.required and merger.default_node_type is None


def test_library_covers_six_control_flow_primitives() -> None:
    # 6 기본형 — 순서(scheduled/event)·루프(quality)·분기·병렬·재시도·승인.
    names = {s.name for s in SKELETONS}
    assert {
        "scheduled_pipeline", "event_response", "quality_loop",
        "branch_on_classification", "fan_out_map", "retry_backoff", "approval_gate",
    } <= names


@pytest.mark.parametrize(
    "name",
    ["scheduled_pipeline", "event_response", "quality_loop",
     "branch_on_classification", "fan_out_map", "retry_backoff", "approval_gate"],
)
def test_find_skeleton(name: str) -> None:
    assert find_skeleton(name) is not None


def test_find_skeleton_unknown_returns_none() -> None:
    assert find_skeleton("nope") is None
