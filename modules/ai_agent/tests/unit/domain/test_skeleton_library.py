"""스켈레톤 라이브러리 그라운딩 가드 (ADR-0026 §6.6 시드 원칙 ①).

슬롯 후보·default node_type이 전부 카탈로그(53종)에 실재하는지 카탈로그 대조로 강제한다.
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


def test_quality_loop_has_generator_and_gate() -> None:
    # quality_gate_loop의 결정적 부활 — transform(generator)+gate(evaluator) 둘 다 required.
    skel = find_skeleton("quality_loop")
    assert skel is not None
    transform = skel.slot(SlotRole.TRANSFORM)
    gate = skel.slot(SlotRole.GATE)
    assert transform is not None and transform.required
    assert gate is not None and gate.required


def test_gate_candidates_are_condition_nodes() -> None:
    # gate = 탈출 조건 condition 노드 — CyclicScheduler/validator 계약(SCC당 condition≥1)의 근거.
    cond = {d.node_type for d in get_all_node_definitions() if d.category == "condition"}
    for skel in SKELETONS:
        gate = skel.slot(SlotRole.GATE)
        if gate is None:
            continue
        for nt in gate.candidates:
            assert nt in cond, f"{skel.name}: gate 후보 {nt}가 condition 노드 아님"


@pytest.mark.parametrize("name", ["scheduled_pipeline", "event_response", "quality_loop"])
def test_find_skeleton(name: str) -> None:
    assert find_skeleton(name) is not None


def test_find_skeleton_unknown_returns_none() -> None:
    assert find_skeleton("nope") is None
