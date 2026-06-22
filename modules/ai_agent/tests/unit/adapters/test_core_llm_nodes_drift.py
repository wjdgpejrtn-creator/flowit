"""범용 LLM 노드 drift 가드 — `_CORE_LLM_NODE_TYPES`가 실제 nodes_graph 카탈로그의
ai 노드와 어긋나면, retriever의 "항상-포함"이 빈 리스트가 되거나(없는 node_type) 새
ai 노드를 누락한다. 이 테스트가 그 drift를 결정적으로 잡는다(`test_structural_categories_drift`
와 동류 — #378/평가 진단 ②).

`_CORE_LLM_NODE_TYPES`의 노드는 (1) 카탈로그에 실재 (2) category=='ai' (3) 실행가능
(EXECUTABLE_NODE_TYPES)여야 한다. 또 카탈로그의 ai 노드 전체를 빠짐없이 덮어야 한다
(새 범용 LLM 노드 추가 시 동기화 강제).
"""
from __future__ import annotations

from nodes_graph.application.catalog_registry import get_all_node_definitions
from nodes_graph.application.executable_node_types import EXECUTABLE_NODE_TYPES

from ai_agent.adapters.langgraph.composer_graph import _CORE_LLM_NODE_TYPES


def _ai_node_types_from_catalog() -> set[str]:
    return {d.node_type for d in get_all_node_definitions() if d.category == "ai"}


def test_core_llm_nodes_exist_and_executable():
    """_CORE_LLM_NODE_TYPES는 전부 카탈로그 실재 + category=='ai' + 실행가능."""
    by_type = {d.node_type: d.category for d in get_all_node_definitions()}
    for nt in _CORE_LLM_NODE_TYPES:
        assert nt in by_type, f"카탈로그에 없는 node_type: {nt}"
        assert by_type[nt] == "ai", f"{nt} category가 'ai' 아님: {by_type[nt]}"
        assert nt in EXECUTABLE_NODE_TYPES, f"{nt}이 실행가능 카탈로그에 없음"


def test_core_llm_nodes_cover_all_ai_category():
    """카탈로그의 ai 카테고리 노드 전체를 _CORE_LLM_NODE_TYPES가 덮는다(새 범용 LLM 노드 동기화 강제)."""
    catalog_ai = _ai_node_types_from_catalog()
    declared = set(_CORE_LLM_NODE_TYPES)
    assert declared == catalog_ai, (
        f"drift — 누락: {sorted(catalog_ai - declared)}, "
        f"미상(카탈로그에 없는 선언): {sorted(declared - catalog_ai)}. "
        f"nodes_graph 카탈로그 ai 노드 변경 시 composer_graph._CORE_LLM_NODE_TYPES 동기화 필요."
    )
