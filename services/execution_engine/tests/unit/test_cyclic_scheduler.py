"""CyclicScheduler 단위 테스트 — ADR-0023 L3 응축/루프 플래닝."""
from __future__ import annotations

from uuid import uuid4

import pytest
from common_schemas.enums import ErrorCode
from common_schemas.exceptions import ValidationError
from common_schemas.workflow import Edge, NodeInstance, Position, WorkflowSchema
from src.domain.services.cyclic_scheduler import DEFAULT_MAX_ITERATIONS, CyclicScheduler


def _node(params=None):
    return NodeInstance(
        instance_id=uuid4(), node_id=uuid4(),
        parameters=params or {}, position=Position(x=0, y=0),
    )


def _edge(frm, to, fh="output", th="input"):
    return Edge(from_instance_id=frm.instance_id, to_instance_id=to.instance_id,
                from_handle=fh, to_handle=th)


def _wf(nodes, edges):
    return WorkflowSchema(
        workflow_id=uuid4(), name="wf", scope="private", is_draft=False,
        nodes=nodes, connections=edges,
    )


class TestAcyclicPassthrough:
    def test_pure_dag_emits_only_level_steps(self):
        a, b, c = _node(), _node(), _node()
        wf = _wf([a, b, c], [_edge(a, b), _edge(b, c)])
        steps = CyclicScheduler().plan(wf, {a.instance_id: False, b.instance_id: False, c.instance_id: False})

        assert [s.kind for s in steps] == ["level", "level", "level"]
        # 위상정렬 그대로: A → B → C
        assert [n.instance_id for n in steps[0].level.nodes] == [a.instance_id]
        assert steps[2].level.nodes[0].instance_id == c.instance_id

    def test_parallel_nodes_grouped_in_one_level(self):
        a, b, c = _node(), _node(), _node()
        wf = _wf([a, b, c], [_edge(a, b), _edge(a, c)])
        steps = CyclicScheduler().plan(wf, {n.instance_id: False for n in (a, b, c)})

        assert [s.kind for s in steps] == ["level", "level"]
        assert {n.instance_id for n in steps[1].level.nodes} == {b.instance_id, c.instance_id}


class TestLoopPlanning:
    def test_simple_loop_emits_loop_step(self):
        # E → S → C, back-edge C→S(retry), exit C→X(done)
        e, s, c, x = _node(), _node(), _node(), _node()
        wf = _wf(
            [e, s, c, x],
            [_edge(e, s), _edge(s, c), _edge(c, s, fh="retry"), _edge(c, x, fh="done")],
        )
        is_brancher = {e.instance_id: False, s.instance_id: False,
                       c.instance_id: True, x.instance_id: False}
        steps = CyclicScheduler().plan(wf, is_brancher)

        kinds = [st.kind for st in steps]
        assert kinds == ["level", "loop", "level"]
        # 진입 E, 탈출 X는 trivial level
        assert steps[0].level.nodes[0].instance_id == e.instance_id
        assert steps[2].level.nodes[0].instance_id == x.instance_id

        loop = steps[1].loop
        # 바디 sub-DAG: S(level0) → C(level1)
        assert [n.instance_id for n in loop.levels[0].nodes] == [s.instance_id]
        assert [n.instance_id for n in loop.levels[1].nodes] == [c.instance_id]
        # back-edge / exit-edge 분리
        assert len(loop.back_edges) == 1
        assert loop.back_edges[0].from_instance_id == c.instance_id
        assert loop.back_edges[0].to_instance_id == s.instance_id
        assert len(loop.exit_edges) == 1
        assert loop.exit_edges[0].to_instance_id == x.instance_id

    def test_max_iterations_from_condition_param(self):
        s = _node()
        c = _node({"max_iterations": 3})
        wf = _wf([s, c], [_edge(s, c), _edge(c, s, fh="retry")])
        steps = CyclicScheduler().plan(wf, {s.instance_id: False, c.instance_id: True})

        assert steps[0].kind == "loop"
        assert steps[0].loop.max_iterations == 3

    def test_max_iterations_defaults_when_absent(self):
        s = _node()
        c = _node()
        wf = _wf([s, c], [_edge(s, c), _edge(c, s, fh="retry")])
        steps = CyclicScheduler().plan(wf, {s.instance_id: False, c.instance_id: True})

        assert steps[0].loop.max_iterations == DEFAULT_MAX_ITERATIONS

    def test_self_loop_single_node(self):
        c = _node({"max_iterations": 2})
        wf = _wf([c], [_edge(c, c, fh="retry")])
        steps = CyclicScheduler().plan(wf, {c.instance_id: True})

        assert steps[0].kind == "loop"
        assert [n.instance_id for n in steps[0].loop.levels[0].nodes] == [c.instance_id]
        assert len(steps[0].loop.back_edges) == 1


class TestNonEscapableCycleRejected:
    def test_cycle_without_condition_raises(self):
        a, b = _node(), _node()
        wf = _wf([a, b], [_edge(a, b), _edge(b, a)])
        with pytest.raises(ValidationError) as exc:
            CyclicScheduler().plan(wf, {a.instance_id: False, b.instance_id: False})
        assert exc.value.code == ErrorCode.E_CYCLE_DETECTED
