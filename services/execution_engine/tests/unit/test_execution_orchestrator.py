"""ExecutionOrchestrator 단위 테스트 — 순수 비즈니스 규칙 검증."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from common_schemas.enums import ExecutionStatus
from common_schemas.exceptions import ExecutionError
from common_schemas.workflow import Edge, NodeInstance, Position, WorkflowSchema

from src.domain.entities.execution_result import NodeResult
from src.domain.services.execution_orchestrator import ExecutionOrchestrator
from src.domain.services.topological_scheduler import TopologicalScheduler


def _make_node():
    return NodeInstance(
        instance_id=uuid4(),
        node_id=uuid4(),
        parameters={},
        position=Position(x=0, y=0),
    )


def _make_workflow(nodes, edges):
    connections = [
        Edge(from_instance_id=frm, to_instance_id=to, from_handle="output", to_handle="input")
        for frm, to in edges
    ]
    return WorkflowSchema(
        workflow_id=uuid4(),
        name="test",
        scope="private",
        is_draft=False,
        nodes=nodes,
        connections=connections,
    )


def _make_node_result(status="succeeded"):
    return NodeResult(
        node_instance_id=uuid4(),
        status=status,
        output={},
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def orchestrator():
    return ExecutionOrchestrator(TopologicalScheduler())


class TestPlan:
    def test_linear_workflow(self, orchestrator):
        a, b = _make_node(), _make_node()
        wf = _make_workflow([a, b], [(a.instance_id, b.instance_id)])

        levels = orchestrator.plan(wf)

        assert len(levels) == 2
        assert levels[0].nodes[0].instance_id == a.instance_id
        assert levels[1].nodes[0].instance_id == b.instance_id

    def test_parallel_nodes(self, orchestrator):
        a, b, c = _make_node(), _make_node(), _make_node()
        wf = _make_workflow(
            [a, b, c],
            [(a.instance_id, b.instance_id), (a.instance_id, c.instance_id)],
        )

        levels = orchestrator.plan(wf)

        assert len(levels) == 2
        level1_ids = {n.instance_id for n in levels[1].nodes}
        assert b.instance_id in level1_ids
        assert c.instance_id in level1_ids

    def test_cycle_raises(self, orchestrator):
        a, b = _make_node(), _make_node()
        wf = _make_workflow(
            [a, b],
            [(a.instance_id, b.instance_id), (b.instance_id, a.instance_id)],
        )

        with pytest.raises(Exception, match="순환"):
            orchestrator.plan(wf)

    def test_invalid_graph_raises(self, orchestrator):
        a = _make_node()
        phantom_id = uuid4()
        wf = WorkflowSchema(
            workflow_id=uuid4(),
            name="test",
            scope="private",
            is_draft=False,
            nodes=[a],
            connections=[
                Edge(
                    from_instance_id=a.instance_id,
                    to_instance_id=phantom_id,
                    from_handle="output",
                    to_handle="input",
                ),
            ],
        )

        with pytest.raises(ExecutionError, match="유효하지"):
            orchestrator.plan(wf)


class TestHasFailures:
    def test_no_failures(self, orchestrator):
        results = [_make_node_result("succeeded"), _make_node_result("succeeded")]
        assert orchestrator.has_failures(results) is False

    def test_with_failure(self, orchestrator):
        results = [_make_node_result("succeeded"), _make_node_result("failed")]
        assert orchestrator.has_failures(results) is True

    def test_empty_list(self, orchestrator):
        assert orchestrator.has_failures([]) is False


class TestValidateStateTransition:
    def test_running_to_paused(self, orchestrator):
        orchestrator.validate_state_transition(
            ExecutionStatus.RUNNING, ExecutionStatus.PAUSED,
        )

    def test_running_to_completed(self, orchestrator):
        orchestrator.validate_state_transition(
            ExecutionStatus.RUNNING, ExecutionStatus.COMPLETED,
        )

    def test_running_to_failed(self, orchestrator):
        orchestrator.validate_state_transition(
            ExecutionStatus.RUNNING, ExecutionStatus.FAILED,
        )

    def test_paused_to_running(self, orchestrator):
        orchestrator.validate_state_transition(
            ExecutionStatus.PAUSED, ExecutionStatus.RUNNING,
        )

    def test_invalid_completed_to_running(self, orchestrator):
        with pytest.raises(ExecutionError, match="Cannot transition"):
            orchestrator.validate_state_transition(
                ExecutionStatus.COMPLETED, ExecutionStatus.RUNNING,
            )

    def test_invalid_paused_to_completed(self, orchestrator):
        with pytest.raises(ExecutionError, match="Cannot transition"):
            orchestrator.validate_state_transition(
                ExecutionStatus.PAUSED, ExecutionStatus.COMPLETED,
            )
