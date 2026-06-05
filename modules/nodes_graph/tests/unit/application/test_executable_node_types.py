"""EXECUTABLE_NODE_TYPES drift 가드 — get_all_node_classes() 키와 정확히 일치해야 한다.

의존성 없는 문자열 미러(`executable_node_types.py`)가 실제 실행 클래스 레지스트리와
어긋나면 Composer가 (a) 실행 가능한 노드를 잘못 필터하거나 (b) 실행 불가 노드를 통과시킨다.
이 테스트가 그 drift를 결정적으로 잡는다 (#378 그라운딩 가드).
"""
from __future__ import annotations

from nodes_graph.application.catalog_registry import get_all_node_classes
from nodes_graph.application.executable_node_types import EXECUTABLE_NODE_TYPES


def test_executable_node_types_matches_registry_exactly():
    registry = set(get_all_node_classes().keys())
    assert EXECUTABLE_NODE_TYPES == registry, (
        f"drift — registry에만: {registry - EXECUTABLE_NODE_TYPES}, "
        f"미러에만: {EXECUTABLE_NODE_TYPES - registry}"
    )


def test_executable_node_types_is_frozenset_of_str():
    assert isinstance(EXECUTABLE_NODE_TYPES, frozenset)
    assert all(isinstance(nt, str) for nt in EXECUTABLE_NODE_TYPES)
    assert len(EXECUTABLE_NODE_TYPES) == 53
