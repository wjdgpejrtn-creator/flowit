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
    celery_task_id: str | None = None,
) -> ExecutionResult:
    return ExecutionResult(
        execution_id=uuid4(),
        workflow_id=uuid4(),
        user_id=uuid4(),
        status=status,
        celery_task_id=celery_task_id,
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

    def test_resume_dispatches_when_task_queue_present(
        self, use_case_with_queue, mock_execution_repo, mock_task_queue,
    ):
        result = _make_result(ExecutionStatus.PAUSED)
        mock_execution_repo.get.return_value = result

        use_case_with_queue.execute(result.execution_id, "resume")

        mock_task_queue.dispatch.assert_called_once()
        call = mock_task_queue.dispatch.call_args
        assert call.args[0] == "execution_engine.execute_workflow"
        ctx = call.kwargs["args"]
        assert ctx["workflow_id"] == str(result.workflow_id)
        assert ctx["context_data"]["execution_id"] == str(result.execution_id)
        assert ctx["context_data"]["trigger_type"] == "resume"
        assert ctx["__queue__"] == "default"


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
        result = _make_result(ExecutionStatus.RUNNING, celery_task_id="celery-task-xyz")
        mock_execution_repo.get.return_value = result

        use_case_with_queue.execute(result.execution_id, "cancel")

        mock_task_queue.revoke.assert_called_once_with("celery-task-xyz", terminate=True)

    def test_cancel_skips_revoke_when_task_id_missing(
        self, use_case_with_queue, mock_execution_repo, mock_task_queue,
    ):
        result = _make_result(ExecutionStatus.RUNNING, celery_task_id=None)
        mock_execution_repo.get.return_value = result

        use_case_with_queue.execute(result.execution_id, "cancel")

        mock_task_queue.revoke.assert_not_called()

    def test_unknown_action_raises(self, use_case, mock_execution_repo):
        result = _make_result(ExecutionStatus.RUNNING)
        mock_execution_repo.get.return_value = result

        with pytest.raises(ValueError, match="Unknown action"):
            use_case.execute(result.execution_id, "bogus")  # type: ignore[arg-type]
