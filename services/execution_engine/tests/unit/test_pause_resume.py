"""PauseResumeUseCase 단위 테스트 — 일시 중지/재개 상태 전환."""
from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from common_schemas.enums import ExecutionStatus
from common_schemas.exceptions import ExecutionError

from src.application.use_cases.pause_resume import PauseResumeUseCase
from src.domain.entities.execution_result import ExecutionResult


@pytest.fixture
def mock_execution_repo():
    return MagicMock()


@pytest.fixture
def mock_events():
    return MagicMock()


@pytest.fixture
def use_case(mock_execution_repo, mock_events):
    return PauseResumeUseCase(
        execution_repo=mock_execution_repo,
        event_publisher=mock_events,
    )


def _make_result(status: ExecutionStatus = ExecutionStatus.RUNNING) -> ExecutionResult:
    return ExecutionResult(
        execution_id=uuid4(),
        workflow_id=uuid4(),
        status=status,
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

        with pytest.raises(ExecutionError, match="Cannot pause"):
            use_case.execute(result.execution_id, "pause")

    def test_pause_already_paused_raises(self, use_case, mock_execution_repo):
        result = _make_result(ExecutionStatus.PAUSED)
        mock_execution_repo.get.return_value = result

        with pytest.raises(ExecutionError, match="Cannot pause"):
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

        with pytest.raises(ExecutionError, match="Cannot resume"):
            use_case.execute(result.execution_id, "resume")

    def test_resume_with_approval(self, use_case, mock_execution_repo, mock_events):
        result = _make_result(ExecutionStatus.PAUSED)
        mock_execution_repo.get.return_value = result

        use_case.execute(result.execution_id, "resume", approval={"approved_by": "admin"})

        saved = mock_execution_repo.save.call_args[0][0]
        assert saved.status == ExecutionStatus.RUNNING
