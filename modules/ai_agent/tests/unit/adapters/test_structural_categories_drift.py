"""구조 노드 category drift 가드 — `_STRUCTURAL_CATEGORIES`가 실제 nodes_graph 카탈로그와
어긋나면 `list_structural()`이 조용히 빈 리스트를 반환해 #378(트리거/분기/루프 누락 하드페일)이
green 테스트로 은폐된다. 이 테스트가 그 drift를 결정적으로 잡는다(#387 EXECUTABLE_NODE_TYPES
drift 가드와 동류).

`category` 필드는 박아름이 소유한 nodes_graph 카탈로그가 SSOT다. 컨벤션이 바뀌면(예: 디렉토리명
'control'에 맞춰 category를 'control'로 변경) 여기서 빨갛게 떠 `_STRUCTURAL_CATEGORIES` 동기화를
강제한다.
"""
from __future__ import annotations

from nodes_graph.application.catalog_registry import get_all_node_definitions

from ai_agent.adapters.node_registry_adapter import _STRUCTURAL_CATEGORIES

# 실행엔진이 트리거/분기/루프로 다루는 14종(트리거 6 + 제어흐름 8). retriever가 의미검색에서
# 놓쳐도 항상 후보로 노출돼야 하는 노드들 — 이 집합이 structural로 분류되지 않으면 #378 재발.
_EXPECTED_STRUCTURAL = frozenset({
    # 트리거 6
    "schedule_trigger", "manual_trigger", "webhook_trigger",
    "event_trigger", "api_poll_trigger", "file_watch_trigger",
    # 제어흐름 8
    "if_condition", "switch_case", "loop_count", "loop_list",
    "merge_branch", "stop_workflow", "retry", "delay",
})


def _structural_node_types_from_catalog() -> set[str]:
    """실 카탈로그에서 `_STRUCTURAL_CATEGORIES` 기준으로 structural 분류되는 node_type."""
    return {
        d.node_type
        for d in get_all_node_definitions()
        if d.category in _STRUCTURAL_CATEGORIES
    }


def test_structural_categories_cover_all_expected_nodes():
    """기대 구조 노드 14종이 실 카탈로그 category 기준으로 전부 structural로 분류된다."""
    classified = _structural_node_types_from_catalog()
    missing = _EXPECTED_STRUCTURAL - classified
    assert not missing, (
        f"category drift — 구조 노드인데 _STRUCTURAL_CATEGORIES로 안 잡힘: {sorted(missing)}. "
        f"nodes_graph 카탈로그 category 변경 시 node_registry_adapter._STRUCTURAL_CATEGORIES 동기화 필요."
    )


def test_structural_classification_is_exactly_expected():
    """structural 분류 결과가 기대 14종과 정확히 일치(초과·누락 0) — 콘텐츠 노드 오분류도 차단."""
    classified = _structural_node_types_from_catalog()
    assert classified == _EXPECTED_STRUCTURAL, (
        f"누락: {sorted(_EXPECTED_STRUCTURAL - classified)}, "
        f"초과(콘텐츠 노드 오분류 의심): {sorted(classified - _EXPECTED_STRUCTURAL)}"
    )


def test_key_trigger_and_control_categories_are_stable():
    """#378 핵심 노드의 실제 category 값 고정 — schedule_trigger='trigger', if_condition/loop_count='condition'."""
    by_type = {d.node_type: d.category for d in get_all_node_definitions()}
    assert by_type["schedule_trigger"] == "trigger"
    assert by_type["if_condition"] == "condition"
    assert by_type["loop_count"] == "condition"
