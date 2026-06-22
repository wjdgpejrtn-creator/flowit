"""PauseResumeUseCase 단위 테스트 — 일시 중지/재개 상태 전환."""
from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from common_schemas.enums import ExecutionStatus
from common_schemas.exceptions import ExecutionError
from src.application.use_cases.pause_resume import PauseResumeUseCase
from src.domain.entities.execution_result import ExecutionResult
from src.domain.services.execution_orchestrator import ExecutionOrchestrator
from src.domain.services.topological_scheduler import TopologicalScheduler


@pytest.fixture
def mock_execution_repo():
    return MagicMock()


@pytest.fixture
def mock_events():
    return MagicMock()


@pytest.fixture
def orchestrator():
    return ExecutionOrchestrator(TopologicalScheduler())


@pytest.fixture
def mock_task_queue():
    return MagicMock()


@pytest.fixture
def use_case(mock_execution_repo, mock_events, orchestrator):
    return PauseResumeUseCase(
        execution_repo=mock_execution_repo,
        event_publisher=mock_events,
        orchestrator=orchestrator,
    )


@pytest.fixture
def use_case_with_queue(mock_execution_repo, mock_events, orchestrator, mock_task_queue):
    return PauseResumeUseCase(
        execution_repo=mock_execution_repo,
        event_publisher=mock_events,
        orchestrator=orchestrator,
        task_queue=mock_task_queue,
    )


def _make_result(
    status: ExecutionStatus = ExecutionStatus.RUNNING,
    task_queue_id: str | None = None,
) -> ExecutionResult:
    return ExecutionResult(
        execution_id=uuid4(),
        workflow_id=uuid4(),
        user_id=uuid4(),
        status=status,
        task_queue_id=task_queue_id,
    )


class TestPause:
    def test_pause_running_execution(self, use_case, mock_execution_repo, mock_events):
        result = _make_result(ExecutionStatus.RUNNING)
        mock_execution_repo.get.return_value = result

        use_case.execute(result.execution_id, "pause")

        mock_execution_repo.save.assert_called_once()
        saved = mock_execution_repo.save.call_args[0][0]
        assert saved.status == ExecutionStatus.PAUSED
        mock_events.publish_status.assert_called_once_with(
            result.execution_id, ExecutionStatus.PAUSED,
        )

    def test_pause_non_running_raises(self, use_case, mock_execution_repo):
        result = _make_result(ExecutionStatus.COMPLETED)
        mock_execution_repo.get.return_value = result

        with pytest.raises(ExecutionError, match="Cannot transition"):
            use_case.execute(result.execution_id, "pause")

    def test_pause_already_paused_raises(self, use_case, mock_execution_repo):
        result = _make_result(ExecutionStatus.PAUSED)
        mock_execution_repo.get.return_value = result

        with pytest.raises(ExecutionError, match="Cannot transition"):
            use_case.execute(result.execution_id, "pause")


class TestResume:
    def test_resume_paused_execution(self, use_case, mock_execution_repo, mock_events):
        result = _make_result(ExecutionStatus.PAUSED)
        mock_execution_repo.get.return_value = result

        use_case.execute(result.execution_id, "resume")

        mock_execution_repo.save.assert_called_once()
        saved = mock_execution_repo.save.call_args[0][0]
        assert saved.status == ExecutionStatus.RUNNING
        mock_events.publish_status.assert_called_once_with(
            result.execution_id, ExecutionStatus.RUNNING,
        )

    def test_resume_non_paused_raises(self, use_case, mock_execution_repo):
        result = _make_result(ExecutionStatus.RUNNING)
        mock_execution_repo.get.return_value = result

        with pytest.raises(ExecutionError, match="Cannot transition"):
            use_case.execute(result.execution_id, "resume")

    def test_resume_with_approval(self, use_case, mock_execution_repo, mock_events):
        result = _make_result(ExecutionStatus.PAUSED)
        mock_execution_repo.get.return_value = result

        use_case.execute(result.execution_id, "resume", approval={"approved_by": "admin"})

        saved = mock_execution_repo.save.call_args[0][0]
        assert saved.status == ExecutionStatus.RUNNING

    def test_resume_dispatches_workflow_when_task_queue_present(
        self, use_case_with_queue, mock_execution_repo, mock_task_queue,
    ):
        result = _make_result(ExecutionStatus.PAUSED, task_queue_id="old-task-id")
        mock_execution_repo.get.return_value = result
        mock_task_queue.dispatch_workflow.return_value = "new-task-id"

        use_case_with_queue.execute(result.execution_id, "resume")

        mock_task_queue.dispatch_workflow.assert_called_once_with(
            execution_id=result.execution_id,
            workflow_id=result.workflow_id,
            user_id=result.user_id,
            trigger_type="resume",
            parameters={},
        )

    def test_resume_replaces_old_task_id_with_new(
        self, use_case_with_queue, mock_execution_repo, mock_task_queue,
    ):
        # resume 후 cancel 시 옛 task_id로 revoke를 시도해 "cancel 안 됨" 버그를 막는 핵심 케이스.
        # 새 task_id로 task_queue_id를 갱신 → 이후 cancel 경로는 현 task를 정확히 가리킨다.
        result = _make_result(ExecutionStatus.PAUSED, task_queue_id="old-task-id")
        mock_execution_repo.get.return_value = result
        mock_task_queue.dispatch_workflow.return_value = "new-task-id"

        use_case_with_queue.execute(result.execution_id, "resume")

        # dispatch 후 한 번만 save — 옛 task_id가 잔존하지 않도록 새 id로 명시 교체.
        mock_execution_repo.save.assert_called_once()
        saved = mock_execution_repo.save.call_args.args[0]
        assert saved.status == ExecutionStatus.RUNNING
        assert saved.task_queue_id == "new-task-id"

    def test_resume_dispatch_failure_keeps_paused(
        self, use_case_with_queue, mock_execution_repo, mock_task_queue,
    ):
        result = _make_result(ExecutionStatus.PAUSED, task_queue_id="old-task-id")
        mock_execution_repo.get.return_value = result
        mock_task_queue.dispatch_workflow.side_effect = RuntimeError("broker down")

        with pytest.raises(RuntimeError):
            use_case_with_queue.execute(result.execution_id, "resume")

        mock_execution_repo.save.assert_not_called()
        # status 미전환 → 호출자가 안전하게 재시도 가능
        assert result.status == ExecutionStatus.PAUSED
        assert result.task_queue_id == "old-task-id"


class TestCancel:
    def test_cancel_running_execution(self, use_case, mock_execution_repo, mock_events):
        result = _make_result(ExecutionStatus.RUNNING)
        mock_execution_repo.get.return_value = result

        use_case.execute(result.execution_id, "cancel")

        saved = mock_execution_repo.save.call_args[0][0]
        assert saved.status == ExecutionStatus.CANCELLED
        assert saved.completed_at is not None
        mock_events.publish_status.assert_called_once_with(
            result.execution_id, ExecutionStatus.CANCELLED,
        )

    def test_cancel_paused_execution(self, use_case, mock_execution_repo):
        result = _make_result(ExecutionStatus.PAUSED)
        mock_execution_repo.get.return_value = result

        use_case.execute(result.execution_id, "cancel")

        saved = mock_execution_repo.save.call_args[0][0]
        assert saved.status == ExecutionStatus.CANCELLED

    def test_cancel_completed_raises(self, use_case, mock_execution_repo):
        result = _make_result(ExecutionStatus.COMPLETED)
        mock_execution_repo.get.return_value = result

        with pytest.raises(ExecutionError, match="Cannot transition"):
            use_case.execute(result.execution_id, "cancel")

    def test_cancel_revokes_celery_task_when_id_present(
        self, use_case_with_queue, mock_execution_repo, mock_task_queue,
    ):
        result = _make_result(ExecutionStatus.RUNNING, task_queue_id="celery-task-xyz")
        mock_execution_repo.get.return_value = result

        use_case_with_queue.execute(result.execution_id, "cancel")

        mock_task_queue.revoke.assert_called_once_with("celery-task-xyz", terminate=True)

    def test_cancel_skips_revoke_when_task_id_missing(
        self, use_case_with_queue, mock_execution_repo, mock_task_queue,
    ):
        result = _make_result(ExecutionStatus.RUNNING, task_queue_id=None)
        mock_execution_repo.get.return_value = result

        use_case_with_queue.execute(result.execution_id, "cancel")

        mock_task_queue.revoke.assert_not_called()

    def test_unknown_action_raises(self, use_case, mock_execution_repo):
        result = _make_result(ExecutionStatus.RUNNING)
        mock_execution_repo.get.return_value = result

        with pytest.raises(ValueError, match="Unknown action"):
            use_case.execute(result.execution_id, "bogus")  # type: ignore[arg-type]
