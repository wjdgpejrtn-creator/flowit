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
    scheduler = TopologicalScheduler()
    orchestrator = ExecutionOrchestrator(scheduler)
    return ExecuteWorkflowUseCase(
        workflow_repo=mock_workflow_repo,
        execution_repo=mock_execution_repo,
        orchestrator=orchestrator,
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


class TestExecuteWorkflowDataflow:
    """ADR-0023 L1 — 상류 출력이 하류 노드 파라미터 ${ref}로 흐르는지 검증."""

    def test_ref_resolved_from_upstream_output(
        self, use_case, mock_workflow_repo, mock_dispatch_node
    ):
        from datetime import datetime, timezone

        a = _make_node()
        b = NodeInstance(
            instance_id=uuid4(), node_id=uuid4(),
            parameters={"text": f"${{{a.instance_id}.summary}}"}, position=Position(x=0, y=0),
        )
        wf = _make_workflow([a, b], [(a.instance_id, b.instance_id)])
        context = _make_context(wf.workflow_id)

        mock_workflow_repo.get.return_value = wf
        mock_workflow_repo.get_node_config.return_value = MagicMock(spec=NodeConfig)
        a_result = NodeResult(
            node_instance_id=a.instance_id, status="succeeded", output={"summary": "요약본"},
            started_at=datetime.now(timezone.utc), completed_at=datetime.now(timezone.utc),
        )
        mock_dispatch_node.execute.side_effect = [a_result, _make_node_result(b)]

        use_case.execute(wf.workflow_id, context)

        # B의 dispatch에 넘어간 노드는 resolved 파라미터를 가져야 함
        b_call = mock_dispatch_node.execute.call_args_list[1]
        passed_node = b_call.kwargs["node"]
        assert passed_node.instance_id == b.instance_id
        assert passed_node.parameters["text"] == "요약본"


class TestExecuteWorkflowBranching:
    """ADR-0023 L2 — 조건 노드 분기: 안 탄 가지 노드는 skip."""

    def test_condition_skips_not_taken_branch(
        self, use_case, mock_workflow_repo, mock_dispatch_node
    ):
        from datetime import UTC, datetime

        c, t, f = _make_node(), _make_node(), _make_node()
        wf = WorkflowSchema(
            workflow_id=uuid4(), name="wf", scope="private", is_draft=False,
            nodes=[c, t, f],
            connections=[
                Edge(from_instance_id=c.instance_id, to_instance_id=t.instance_id,
                     from_handle="true", to_handle="input"),
                Edge(from_instance_id=c.instance_id, to_instance_id=f.instance_id,
                     from_handle="false", to_handle="input"),
            ],
        )
        context = _make_context(wf.workflow_id)

        cond_cfg = MagicMock(spec=NodeConfig)
        cond_cfg.category = "condition"
        plain_cfg = MagicMock(spec=NodeConfig)
        plain_cfg.category = "action"
        mock_workflow_repo.get.return_value = wf
        mock_workflow_repo.get_node_config.side_effect = (
            lambda nid: cond_cfg if nid == c.node_id else plain_cfg
        )
        c_result = NodeResult(
            node_instance_id=c.instance_id, status="succeeded",
            output={"branch": "true", "value": 1},
            started_at=datetime.now(UTC), completed_at=datetime.now(UTC),
        )
        # c와 t만 dispatch — f는 skip되어 dispatch 안 됨
        mock_dispatch_node.execute.side_effect = [c_result, _make_node_result(t)]

        result = use_case.execute(wf.workflow_id, context)

        statuses = {r.node_instance_id: r.status for r in result.node_results}
        assert statuses[c.instance_id] == "succeeded"
        assert statuses[t.instance_id] == "succeeded"
        assert statuses[f.instance_id] == "skipped"
        assert result.status == ExecutionStatus.COMPLETED
        dispatched = [call.kwargs["node"].instance_id for call in mock_dispatch_node.execute.call_args_list]
        assert f.instance_id not in dispatched


class TestExecuteWorkflowLoop:
    """ADR-0023 L3 — 유한 순환(품질게이트 루프)."""

    @staticmethod
    def _loop_wf():
        """S → C(condition), back-edge C→S(retry), exit C→X(done)."""
        s, c, x = _make_node(), _make_node(), _make_node()
        wf = WorkflowSchema(
            workflow_id=uuid4(), name="loop", scope="private", is_draft=False,
            nodes=[s, c, x],
            connections=[
                Edge(from_instance_id=s.instance_id, to_instance_id=c.instance_id,
                     from_handle="output", to_handle="input"),
                Edge(from_instance_id=c.instance_id, to_instance_id=s.instance_id,
                     from_handle="retry", to_handle="input"),
                Edge(from_instance_id=c.instance_id, to_instance_id=x.instance_id,
                     from_handle="done", to_handle="input"),
            ],
        )
        return s, c, x, wf

    @staticmethod
    def _configs(mock_workflow_repo, wf, c, max_iterations=None):
        cond_cfg = MagicMock(spec=NodeConfig)
        cond_cfg.category = "condition"
        plain_cfg = MagicMock(spec=NodeConfig)
        plain_cfg.category = "action"
        mock_workflow_repo.get.return_value = wf
        mock_workflow_repo.get_node_config.side_effect = (
            lambda nid: cond_cfg if nid == c.node_id else plain_cfg
        )

    @staticmethod
    def _result(node, output, iteration=0):
        from datetime import UTC, datetime
        return NodeResult(
            node_instance_id=node.instance_id, status="succeeded", output=output,
            started_at=datetime.now(UTC), completed_at=datetime.now(UTC), iteration=iteration,
        )

    def test_loop_retries_until_done(self, use_case, mock_workflow_repo, mock_dispatch_node):
        """condition이 retry 2회 후 done → 바디 3회 실행 + 탈출 노드 실행."""
        s, c, x, wf = self._loop_wf()
        # max_iterations를 condition 파라미터에 (넉넉히)
        c = NodeInstance(instance_id=c.instance_id, node_id=c.node_id,
                         parameters={"max_iterations": 5}, position=Position(x=0, y=0))
        wf = WorkflowSchema(**{**wf.model_dump(), "nodes": [s, c, x]})
        context = _make_context(wf.workflow_id)
        self._configs(mock_workflow_repo, wf, c)

        mock_dispatch_node.execute.side_effect = [
            self._result(s, {"summary": "v0"}, 0), self._result(c, {"branch": "retry"}, 0),
            self._result(s, {"summary": "v1"}, 1), self._result(c, {"branch": "retry"}, 1),
            self._result(s, {"summary": "v2"}, 2), self._result(c, {"branch": "done"}, 2),
            self._result(x, {"sent": True}),
        ]

        result = use_case.execute(wf.workflow_id, context)

        assert result.status == ExecutionStatus.COMPLETED
        # S, C 각 3회 + X 1회 = 7 dispatch
        assert mock_dispatch_node.execute.call_count == 7
        s_iters = sorted(r.iteration for r in result.node_results if r.node_instance_id == s.instance_id)
        assert s_iters == [0, 1, 2]
        # 탈출 노드 X 실행됨
        assert any(r.node_instance_id == x.instance_id and r.status == "succeeded"
                   for r in result.node_results)

    def test_loop_force_exits_at_guard(self, use_case, mock_workflow_repo, mock_dispatch_node):
        """가드(max_iterations=2) 도달 → retry 중에도 강제 탈출 + 하류 진행(best-effort)."""
        s, c, x, wf = self._loop_wf()
        c = NodeInstance(instance_id=c.instance_id, node_id=c.node_id,
                         parameters={"max_iterations": 2}, position=Position(x=0, y=0))
        wf = WorkflowSchema(**{**wf.model_dump(), "nodes": [s, c, x]})
        context = _make_context(wf.workflow_id)
        self._configs(mock_workflow_repo, wf, c)

        # condition은 계속 retry만 반환
        mock_dispatch_node.execute.side_effect = [
            self._result(s, {"summary": "v0"}, 0), self._result(c, {"branch": "retry"}, 0),
            self._result(s, {"summary": "v1"}, 1), self._result(c, {"branch": "retry"}, 1),
            self._result(x, {"sent": True}),
        ]

        result = use_case.execute(wf.workflow_id, context)

        # 가드로 멈춤: 바디 2회(S,C ×2) + 강제 exit X = 5 dispatch
        assert result.status == ExecutionStatus.COMPLETED
        assert mock_dispatch_node.execute.call_count == 5
        # X는 condition이 retry였음에도 강제 live로 실행됨
        dispatched = [call.kwargs["node"].instance_id for call in mock_dispatch_node.execute.call_args_list]
        assert x.instance_id in dispatched
