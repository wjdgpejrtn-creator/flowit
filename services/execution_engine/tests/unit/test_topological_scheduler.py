"""TopologicalScheduler 단위 테스트 — Kahn's algorithm 검증."""
from __future__ import annotations

from uuid import uuid4

import pytest

from common_schemas.enums import ErrorCode
from common_schemas.exceptions import ValidationError
from common_schemas.workflow import Edge, NodeInstance, Position, WorkflowSchema

from src.domain.services.topological_scheduler import TopologicalScheduler


def _make_node(instance_id=None):
    return NodeInstance(
        instance_id=instance_id or uuid4(),
        node_id=uuid4(),
        parameters={},
        position=Position(x=0, y=0),
    )


def _make_workflow(nodes: list[NodeInstance], edges: list[tuple]) -> WorkflowSchema:
    connections = [
        Edge(
            from_instance_id=frm,
            to_instance_id=to,
            from_handle="output",
            to_handle="input",
        )
        for frm, to in edges
    ]
    return WorkflowSchema(
        workflow_id=uuid4(),
        name="test_workflow",
        scope="private",
        is_draft=False,
        nodes=nodes,
        connections=connections,
    )


@pytest.fixture
def scheduler():
    return TopologicalScheduler()


class TestValidateDag:
    def test_valid_dag_no_error(self, scheduler):
        """순환 없는 DAG → 예외 없음"""
        a, b, c = _make_node(), _make_node(), _make_node()
        wf = _make_workflow([a, b, c], [(a.instance_id, b.instance_id), (b.instance_id, c.instance_id)])
        scheduler.validate_dag(wf)

    def test_cycle_detected(self, scheduler):
        """순환 참조 → ValidationError(E_CYCLE_DETECTED)"""
        a, b, c = _make_node(), _make_node(), _make_node()
        wf = _make_workflow(
            [a, b, c],
            [
                (a.instance_id, b.instance_id),
                (b.instance_id, c.instance_id),
                (c.instance_id, a.instance_id),
            ],
        )
        with pytest.raises(ValidationError) as exc_info:
            scheduler.validate_dag(wf)
        assert exc_info.value.code == ErrorCode.E_CYCLE_DETECTED

    def test_self_loop_detected(self, scheduler):
        """자기 참조 순환 → ValidationError"""
        a = _make_node()
        wf = _make_workflow([a], [(a.instance_id, a.instance_id)])
        with pytest.raises(ValidationError):
            scheduler.validate_dag(wf)

    def test_empty_workflow(self, scheduler):
        """빈 워크플로우 → 예외 없음"""
        wf = _make_workflow([], [])
        scheduler.validate_dag(wf)


class TestSchedule:
    def test_linear_chain(self, scheduler):
        """A → B → C: 3 레벨, 각 1개 노드"""
        a, b, c = _make_node(), _make_node(), _make_node()
        wf = _make_workflow(
            [a, b, c],
            [(a.instance_id, b.instance_id), (b.instance_id, c.instance_id)],
        )
        levels = scheduler.schedule(wf)

        assert len(levels) == 3
        assert levels[0].level == 0
        assert levels[0].nodes == [a]
        assert levels[1].nodes == [b]
        assert levels[2].nodes == [c]

    def test_parallel_nodes(self, scheduler):
        """A → B, A → C: B와 C는 같은 레벨"""
        a, b, c = _make_node(), _make_node(), _make_node()
        wf = _make_workflow(
            [a, b, c],
            [(a.instance_id, b.instance_id), (a.instance_id, c.instance_id)],
        )
        levels = scheduler.schedule(wf)

        assert len(levels) == 2
        assert levels[0].nodes == [a]
        level_1_ids = {n.instance_id for n in levels[1].nodes}
        assert level_1_ids == {b.instance_id, c.instance_id}

    def test_diamond_shape(self, scheduler):
        """다이아몬드: A → B,C → D"""
        a, b, c, d = _make_node(), _make_node(), _make_node(), _make_node()
        wf = _make_workflow(
            [a, b, c, d],
            [
                (a.instance_id, b.instance_id),
                (a.instance_id, c.instance_id),
                (b.instance_id, d.instance_id),
                (c.instance_id, d.instance_id),
            ],
        )
        levels = scheduler.schedule(wf)

        assert len(levels) == 3
        assert levels[0].nodes == [a]
        level_1_ids = {n.instance_id for n in levels[1].nodes}
        assert level_1_ids == {b.instance_id, c.instance_id}
        assert levels[2].nodes == [d]

    def test_multiple_roots(self, scheduler):
        """여러 시작 노드: A, B (독립) → 같은 레벨 0"""
        a, b = _make_node(), _make_node()
        wf = _make_workflow([a, b], [])
        levels = scheduler.schedule(wf)

        assert len(levels) == 1
        assert levels[0].level == 0
        level_0_ids = {n.instance_id for n in levels[0].nodes}
        assert level_0_ids == {a.instance_id, b.instance_id}

    def test_complex_graph(self, scheduler):
        """복잡 그래프: 5노드, 여러 의존관계"""
        a, b, c, d, e = [_make_node() for _ in range(5)]
        wf = _make_workflow(
            [a, b, c, d, e],
            [
                (a.instance_id, c.instance_id),
                (b.instance_id, c.instance_id),
                (c.instance_id, d.instance_id),
                (c.instance_id, e.instance_id),
            ],
        )
        levels = scheduler.schedule(wf)

        assert len(levels) == 3
        level_0_ids = {n.instance_id for n in levels[0].nodes}
        assert level_0_ids == {a.instance_id, b.instance_id}
        assert levels[1].nodes == [c]
        level_2_ids = {n.instance_id for n in levels[2].nodes}
        assert level_2_ids == {d.instance_id, e.instance_id}

    def test_single_node_no_edges(self, scheduler):
        """단일 노드, 연결 없음"""
        a = _make_node()
        wf = _make_workflow([a], [])
        levels = scheduler.schedule(wf)

        assert len(levels) == 1
        assert levels[0].nodes == [a]

    def test_empty_workflow_returns_empty(self, scheduler):
        """빈 워크플로우 → 빈 레벨 목록"""
        wf = _make_workflow([], [])
        levels = scheduler.schedule(wf)
        assert levels == []
