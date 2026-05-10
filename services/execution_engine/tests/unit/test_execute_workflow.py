"""ExecuteWorkflowUseCase 단위 테스트 — 전체 오케스트레이션 검증."""
from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from common_schemas.enums import ExecutionStatus
from common_schemas.exceptions import ValidationError
from common_schemas.workflow import Edge, NodeConfig, NodeInstance, Position, WorkflowSchema
from common_schemas.enums import RiskLevel

from src.application.use_cases.execute_workflow import ExecuteWorkflowUseCase
from src.domain.entities.execution_context import ExecutionContext
from src.domain.entities.execution_result import NodeResult
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


def _make_context(workflow_id=None):
    return ExecutionContext(
        execution_id=uuid4(),
        workflow_id=workflow_id or uuid4(),
        user_id=uuid4(),
        trigger_type="manual",
    )


def _make_node_result(node, status="succeeded"):
    from datetime import datetime, timezone
    return NodeResult(
        node_instance_id=node.instance_id,
        status=status,
        output={"done": True},
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def mock_workflow_repo():
    return MagicMock()


@pytest.fixture
def mock_execution_repo():
    return MagicMock()


@pytest.fixture
def mock_dispatch_node():
    return MagicMock()


@pytest.fixture
def mock_events():
    return MagicMock()


@pytest.fixture
def use_case(mock_workflow_repo, mock_execution_repo, mock_dispatch_node, mock_events):
    return ExecuteWorkflowUseCase(
        workflow_repo=mock_workflow_repo,
        execution_repo=mock_execution_repo,
        scheduler=TopologicalScheduler(),
        dispatch_node=mock_dispatch_node,
        event_publisher=mock_events,
    )


class TestExecuteWorkflowSuccess:
    def test_linear_workflow_completes(self, use_case, mock_workflow_repo, mock_dispatch_node):
        """A → B 선형 워크플로우 정상 완료"""
        a, b = _make_node(), _make_node()
        wf = _make_workflow([a, b], [(a.instance_id, b.instance_id)])
        context = _make_context(wf.workflow_id)

        mock_workflow_repo.get.return_value = wf
        mock_workflow_repo.get_node_config.return_value = MagicMock(spec=NodeConfig)
        mock_dispatch_node.execute.side_effect = [
            _make_node_result(a),
            _make_node_result(b),
        ]

        result = use_case.execute(wf.workflow_id, context)

        assert result.status == ExecutionStatus.COMPLETED
        assert len(result.node_results) == 2
        assert result.error is None

    def test_parallel_nodes_all_succeed(self, use_case, mock_workflow_repo, mock_dispatch_node):
        """A → (B, C) 병렬 노드 전부 성공"""
        a, b, c = _make_node(), _make_node(), _make_node()
        wf = _make_workflow(
            [a, b, c],
            [(a.instance_id, b.instance_id), (a.instance_id, c.instance_id)],
        )
        context = _make_context(wf.workflow_id)

        mock_workflow_repo.get.return_value = wf
        mock_workflow_repo.get_node_config.return_value = MagicMock(spec=NodeConfig)
        mock_dispatch_node.execute.side_effect = [
            _make_node_result(a),
            _make_node_result(b),
            _make_node_result(c),
        ]

        result = use_case.execute(wf.workflow_id, context)

        assert result.status == ExecutionStatus.COMPLETED
        assert len(result.node_results) == 3

    def test_execution_result_saved(self, use_case, mock_workflow_repo, mock_dispatch_node, mock_execution_repo):
        """실행 결과가 repository에 저장됨"""
        a = _make_node()
        wf = _make_workflow([a], [])
        context = _make_context(wf.workflow_id)

        mock_workflow_repo.get.return_value = wf
        mock_workflow_repo.get_node_config.return_value = MagicMock(spec=NodeConfig)
        mock_dispatch_node.execute.return_value = _make_node_result(a)

        use_case.execute(wf.workflow_id, context)

        mock_execution_repo.save.assert_called_once()


class TestExecuteWorkflowFailure:
    def test_node_failure_stops_execution(self, use_case, mock_workflow_repo, mock_dispatch_node):
        """노드 실패 → 후속 레벨 미실행, status=FAILED"""
        a, b = _make_node(), _make_node()
        wf = _make_workflow([a, b], [(a.instance_id, b.instance_id)])
        context = _make_context(wf.workflow_id)

        mock_workflow_repo.get.return_value = wf
        mock_workflow_repo.get_node_config.return_value = MagicMock(spec=NodeConfig)
        mock_dispatch_node.execute.return_value = _make_node_result(a, status="failed")

        result = use_case.execute(wf.workflow_id, context)

        assert result.status == ExecutionStatus.FAILED
        assert len(result.node_results) == 1
        assert mock_dispatch_node.execute.call_count == 1

    def test_cycle_detection_fails(self, use_case, mock_workflow_repo, mock_dispatch_node):
        """순환 그래프 → FAILED + ValidationError 메시지"""
        a, b = _make_node(), _make_node()
        wf = _make_workflow(
            [a, b],
            [(a.instance_id, b.instance_id), (b.instance_id, a.instance_id)],
        )
        context = _make_context(wf.workflow_id)

        mock_workflow_repo.get.return_value = wf
        mock_workflow_repo.get_node_config.return_value = MagicMock(spec=NodeConfig)

        result = use_case.execute(wf.workflow_id, context)

        assert result.status == ExecutionStatus.FAILED
        assert "순환" in result.error
        mock_dispatch_node.execute.assert_not_called()


class TestEventPublishing:
    def test_status_events_published(self, use_case, mock_workflow_repo, mock_dispatch_node, mock_events):
        """RUNNING과 COMPLETED 이벤트 발행"""
        a = _make_node()
        wf = _make_workflow([a], [])
        context = _make_context(wf.workflow_id)

        mock_workflow_repo.get.return_value = wf
        mock_workflow_repo.get_node_config.return_value = MagicMock(spec=NodeConfig)
        mock_dispatch_node.execute.return_value = _make_node_result(a)

        use_case.execute(wf.workflow_id, context)

        status_calls = mock_events.publish_status.call_args_list
        assert status_calls[0][0][1] == ExecutionStatus.RUNNING
        assert status_calls[1][0][1] == ExecutionStatus.COMPLETED

    def test_node_complete_event_per_node(self, use_case, mock_workflow_repo, mock_dispatch_node, mock_events):
        """노드 완료 시 publish_node_complete 호출"""
        a, b = _make_node(), _make_node()
        wf = _make_workflow([a, b], [])
        context = _make_context(wf.workflow_id)

        mock_workflow_repo.get.return_value = wf
        mock_workflow_repo.get_node_config.return_value = MagicMock(spec=NodeConfig)
        mock_dispatch_node.execute.side_effect = [
            _make_node_result(a),
            _make_node_result(b),
        ]

        use_case.execute(wf.workflow_id, context)

        assert mock_events.publish_node_complete.call_count == 2
