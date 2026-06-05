"""ExecuteWorkflowUseCase 단위 테스트 — 전체 오케스트레이션 검증."""
from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from common_schemas.enums import ExecutionStatus
from common_schemas.exceptions import NotFoundError, ValidationError
from common_schemas.workflow import Edge, NodeConfig, NodeInstance, Position, WorkflowSchema
from common_schemas.enums import RiskLevel

from src.application.use_cases.execute_workflow import ExecuteWorkflowUseCase
from src.domain.entities.execution_context import ExecutionContext
from src.domain.entities.execution_result import ExecutionResult, NodeResult
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
        """실행 결과가 repository에 저장됨.

        ADR-0025로 save 호출이 1회(종료 시점) → 다회(시작 RUNNING row + step별
        체크포인트 + 종료)로 늘었다. 마지막 save가 COMPLETED 최종 상태여야 한다.
        """
        a = _make_node()
        wf = _make_workflow([a], [])
        context = _make_context(wf.workflow_id)

        mock_workflow_repo.get.return_value = wf
        mock_workflow_repo.get_node_config.return_value = MagicMock(spec=NodeConfig)
        mock_dispatch_node.execute.return_value = _make_node_result(a)

        use_case.execute(wf.workflow_id, context)

        assert mock_execution_repo.save.called
        last_saved = mock_execution_repo.save.call_args.args[0]
        assert last_saved.status == ExecutionStatus.COMPLETED


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


def _resume_context(workflow_id, execution_id=None):
    return ExecutionContext(
        execution_id=execution_id or uuid4(),
        workflow_id=workflow_id,
        user_id=uuid4(),
        trigger_type="resume",
    )


def _status_obj(status):
    """execution_repo.get가 돌려줄, .status만 있는 가벼운 더블."""
    obj = MagicMock()
    obj.status = status
    obj.node_results = []
    return obj


class TestCooperativePause:
    """ADR-0025 — step 경계에서 DB status가 PAUSED면 협조적으로 중단한다."""

    def test_pause_at_step_boundary_stops_before_next_level(
        self, use_case, mock_workflow_repo, mock_dispatch_node, mock_execution_repo, mock_events
    ):
        """A→B→C 중 B 진입 직전 PAUSED 감지 → A만 실행하고 중단."""
        a, b, c = _make_node(), _make_node(), _make_node()
        wf = _make_workflow(
            [a, b, c],
            [(a.instance_id, b.instance_id), (b.instance_id, c.instance_id)],
        )
        context = _make_context(wf.workflow_id)

        mock_workflow_repo.get.return_value = wf
        mock_workflow_repo.get_node_config.return_value = MagicMock(spec=NodeConfig)
        mock_dispatch_node.execute.side_effect = [_make_node_result(a)]
        # step A 진입 전: RUNNING → 실행. step B 진입 전: PAUSED → 중단.
        mock_execution_repo.get.side_effect = [
            _status_obj(ExecutionStatus.RUNNING),
            _status_obj(ExecutionStatus.PAUSED),
        ]

        result = use_case.execute(wf.workflow_id, context)

        assert result.status == ExecutionStatus.PAUSED
        assert result.completed_at is None  # 완료/실패 마킹 안 함
        assert mock_dispatch_node.execute.call_count == 1  # A만
        assert len(result.node_results) == 1
        # 마지막 publish_status는 PAUSED
        assert mock_events.publish_status.call_args.args[1] == ExecutionStatus.PAUSED

    def test_no_pause_runs_to_completion(
        self, use_case, mock_workflow_repo, mock_dispatch_node, mock_execution_repo
    ):
        """status가 계속 RUNNING이면 정상 완료(pause 미발동)."""
        a, b = _make_node(), _make_node()
        wf = _make_workflow([a, b], [(a.instance_id, b.instance_id)])
        context = _make_context(wf.workflow_id)

        mock_workflow_repo.get.return_value = wf
        mock_workflow_repo.get_node_config.return_value = MagicMock(spec=NodeConfig)
        mock_dispatch_node.execute.side_effect = [_make_node_result(a), _make_node_result(b)]
        mock_execution_repo.get.return_value = _status_obj(ExecutionStatus.RUNNING)

        result = use_case.execute(wf.workflow_id, context)

        assert result.status == ExecutionStatus.COMPLETED
        assert mock_dispatch_node.execute.call_count == 2


class TestCheckpointResume:
    """ADR-0025 — resume 시 직전 완료 노드를 재디스패치하지 않고 이어 실행한다."""

    def _prior(self, execution_id, workflow_id, succeeded_nodes):
        from datetime import datetime, timezone

        return ExecutionResult(
            execution_id=execution_id,
            workflow_id=workflow_id,
            user_id=uuid4(),
            status=ExecutionStatus.RUNNING,
            node_results=[
                NodeResult(
                    node_instance_id=n.instance_id, status="succeeded",
                    output={"done": True},
                    started_at=datetime.now(timezone.utc),
                    completed_at=datetime.now(timezone.utc),
                )
                for n in succeeded_nodes
            ],
        )

    def test_resume_skips_completed_and_runs_remaining(
        self, use_case, mock_workflow_repo, mock_dispatch_node, mock_execution_repo
    ):
        """A,B 완료 체크포인트 → resume 시 C만 dispatch(A,B 재실행 없음)."""
        a, b, c = _make_node(), _make_node(), _make_node()
        wf = _make_workflow(
            [a, b, c],
            [(a.instance_id, b.instance_id), (b.instance_id, c.instance_id)],
        )
        exec_id = uuid4()
        context = _resume_context(wf.workflow_id, exec_id)

        mock_workflow_repo.get.return_value = wf
        mock_workflow_repo.get_node_config.return_value = MagicMock(spec=NodeConfig)
        # checkpoint 로드 + 매 step pause 체크가 같은 prior(RUNNING)를 받음.
        mock_execution_repo.get.return_value = self._prior(exec_id, wf.workflow_id, [a, b])
        mock_dispatch_node.execute.side_effect = [_make_node_result(c)]

        result = use_case.execute(wf.workflow_id, context)

        assert result.status == ExecutionStatus.COMPLETED
        assert mock_dispatch_node.execute.call_count == 1  # C만
        dispatched = mock_dispatch_node.execute.call_args.kwargs["node"].instance_id
        assert dispatched == c.instance_id
        # 최종 결과엔 복원된 A,B + 신규 C = 3
        assert len(result.node_results) == 3

    def test_resume_republishes_completed_node_events(
        self, use_case, mock_workflow_repo, mock_dispatch_node, mock_execution_repo, mock_events
    ):
        """resume 시 복원 노드도 node_complete 재발행(UI 진행률 복원)."""
        a, b = _make_node(), _make_node()
        wf = _make_workflow([a, b], [(a.instance_id, b.instance_id)])
        exec_id = uuid4()
        context = _resume_context(wf.workflow_id, exec_id)

        mock_workflow_repo.get.return_value = wf
        mock_workflow_repo.get_node_config.return_value = MagicMock(spec=NodeConfig)
        mock_execution_repo.get.return_value = self._prior(exec_id, wf.workflow_id, [a])
        mock_dispatch_node.execute.side_effect = [_make_node_result(b)]

        use_case.execute(wf.workflow_id, context)

        # A(복원) + B(신규 실행) = 2회
        assert mock_events.publish_node_complete.call_count == 2

    def test_resume_with_no_prior_runs_fresh(
        self, use_case, mock_workflow_repo, mock_dispatch_node, mock_execution_repo
    ):
        """체크포인트 조회 실패(row 없음) → 처음부터 전체 실행."""
        a, b = _make_node(), _make_node()
        wf = _make_workflow([a, b], [(a.instance_id, b.instance_id)])
        context = _resume_context(wf.workflow_id)

        mock_workflow_repo.get.return_value = wf
        mock_workflow_repo.get_node_config.return_value = MagicMock(spec=NodeConfig)
        from common_schemas.exceptions import NotFoundError
        mock_execution_repo.get.side_effect = NotFoundError("not found")
        mock_dispatch_node.execute.side_effect = [_make_node_result(a), _make_node_result(b)]

        result = use_case.execute(wf.workflow_id, context)

        assert result.status == ExecutionStatus.COMPLETED
        assert mock_dispatch_node.execute.call_count == 2  # 둘 다 실행


class _StatefulRepo:
    """get/save가 같은 row를 공유하는 fake — 실 Postgres의 status clobber 재현용.

    `save`는 status를 전부 덮어쓰고(EXCLUDED.status), `save_checkpoint`는 node_results만
    갱신하고 status를 보존한다. MagicMock(side_effect로 get/save 독립 스텁)으로는
    이 결합을 재현할 수 없어 clobber 회귀를 못 잡는다 — #380 리뷰 HIGH 대응.
    """

    def __init__(self) -> None:
        self._status: dict = {}
        self._nr: dict = {}

    def save(self, result) -> None:
        self._status[result.execution_id] = result.status  # 전체 덮어쓰기
        self._nr[result.execution_id] = list(result.node_results)

    def save_checkpoint(self, result) -> None:
        self._nr[result.execution_id] = list(result.node_results)  # status 보존

    def get(self, execution_id):
        from types import SimpleNamespace

        if execution_id not in self._status:
            raise NotFoundError("not found")
        return SimpleNamespace(
            status=self._status[execution_id], node_results=self._nr.get(execution_id, [])
        )

    def update_node_state(self, *a, **k) -> None:
        pass

    def external_pause(self, execution_id) -> None:
        """다른 트랜잭션(pause task)이 PAUSED를 쓴 상황을 모사."""
        self._status[execution_id] = ExecutionStatus.PAUSED


class TestPauseClobberRegression:
    """#380 리뷰 HIGH — step별 체크포인트 save가 PAUSED를 RUNNING으로 덮어쓰면 안 된다."""

    def _use_case(self, repo, mock_workflow_repo, mock_dispatch_node, mock_events):
        return ExecuteWorkflowUseCase(
            workflow_repo=mock_workflow_repo,
            execution_repo=repo,
            orchestrator=ExecutionOrchestrator(TopologicalScheduler()),
            dispatch_node=mock_dispatch_node,
            event_publisher=mock_events,
        )

    def test_pause_during_middle_step_is_not_clobbered(
        self, mock_workflow_repo, mock_dispatch_node, mock_events
    ):
        """B 실행 도중 pause 도착 → 체크포인트 save가 status 보존 → C 진입 전 감지."""
        a, b, c = _make_node(), _make_node(), _make_node()
        wf = _make_workflow(
            [a, b, c],
            [(a.instance_id, b.instance_id), (b.instance_id, c.instance_id)],
        )
        context = _make_context(wf.workflow_id)
        repo = _StatefulRepo()
        use_case = self._use_case(repo, mock_workflow_repo, mock_dispatch_node, mock_events)

        mock_workflow_repo.get.return_value = wf
        mock_workflow_repo.get_node_config.return_value = MagicMock(spec=NodeConfig)

        def dispatch(*, node, **kwargs):
            if node.instance_id == b.instance_id:
                repo.external_pause(context.execution_id)  # step 도중 pause 도착
            return _make_node_result(node)

        mock_dispatch_node.execute.side_effect = dispatch

        result = use_case.execute(wf.workflow_id, context)

        assert result.status == ExecutionStatus.PAUSED
        assert repo.get(context.execution_id).status == ExecutionStatus.PAUSED  # clobber 없음
        dispatched = [call.kwargs["node"].instance_id for call in mock_dispatch_node.execute.call_args_list]
        assert c.instance_id not in dispatched  # 다음 step 미진입

    def test_pause_during_last_step_detected_after_loop(
        self, mock_workflow_repo, mock_dispatch_node, mock_events
    ):
        """마지막 step 도중 pause → top-check 못 잡음 → 루프 후 재확인이 잡아 PAUSED."""
        a, b = _make_node(), _make_node()
        wf = _make_workflow([a, b], [(a.instance_id, b.instance_id)])
        context = _make_context(wf.workflow_id)
        repo = _StatefulRepo()
        use_case = self._use_case(repo, mock_workflow_repo, mock_dispatch_node, mock_events)

        mock_workflow_repo.get.return_value = wf
        mock_workflow_repo.get_node_config.return_value = MagicMock(spec=NodeConfig)

        def dispatch(*, node, **kwargs):
            if node.instance_id == b.instance_id:
                repo.external_pause(context.execution_id)
            return _make_node_result(node)

        mock_dispatch_node.execute.side_effect = dispatch

        result = use_case.execute(wf.workflow_id, context)

        assert result.status == ExecutionStatus.PAUSED
        assert result.completed_at is None  # 완료 마킹 안 됨
