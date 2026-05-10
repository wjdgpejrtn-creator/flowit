"""EvaluateAndRefineUseCase 단위 테스트 — QA 평가 → Self-Refine."""
from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from common_schemas.enums import ExecutionStatus
from common_schemas.exceptions import ExecutionError
from common_schemas.handoff import EvaluationResult

from src.application.use_cases.evaluate_and_refine import (
    EvaluateAndRefineUseCase,
    MAX_REFINE_ATTEMPTS,
    PASS_THRESHOLD,
)
from src.domain.entities.execution_result import ExecutionResult


@pytest.fixture
def mock_execution_repo():
    return MagicMock()


@pytest.fixture
def mock_workflow_repo():
    return MagicMock()


@pytest.fixture
def mock_execute_workflow():
    m = MagicMock()
    m.execute.return_value = ExecutionResult(
        execution_id=uuid4(),
        workflow_id=uuid4(),
        status=ExecutionStatus.COMPLETED,
    )
    return m


@pytest.fixture
def use_case(mock_execution_repo, mock_workflow_repo, mock_execute_workflow):
    return EvaluateAndRefineUseCase(
        execution_repo=mock_execution_repo,
        workflow_repo=mock_workflow_repo,
        execute_workflow=mock_execute_workflow,
    )


class TestQAPassed:
    def test_pass_flag_true_returns_none(self, use_case):
        evaluation = EvaluationResult(
            score=9.0, pass_flag=True, reason="Good", feedback="No issues",
        )
        result = use_case.execute(uuid4(), evaluation)
        assert result is None

    def test_high_score_returns_none(self, use_case):
        evaluation = EvaluationResult(
            score=PASS_THRESHOLD, pass_flag=False, reason="Good enough", feedback="OK",
        )
        result = use_case.execute(uuid4(), evaluation)
        assert result is None


class TestQAFailed:
    def test_low_score_triggers_re_execution(
        self, use_case, mock_execution_repo, mock_execute_workflow,
    ):
        eid = uuid4()
        original = ExecutionResult(
            execution_id=eid,
            workflow_id=uuid4(),
            status=ExecutionStatus.COMPLETED,
            node_results=[],
        )
        mock_execution_repo.get.return_value = original

        evaluation = EvaluationResult(
            score=5.0, pass_flag=False, reason="Poor quality", feedback="Needs work",
        )

        result = use_case.execute(eid, evaluation)

        assert result is not None
        assert result.status == ExecutionStatus.COMPLETED
        mock_execute_workflow.execute.assert_called_once()

    def test_re_execution_includes_feedback(
        self, use_case, mock_execution_repo, mock_execute_workflow,
    ):
        eid = uuid4()
        original = ExecutionResult(
            execution_id=eid,
            workflow_id=uuid4(),
            status=ExecutionStatus.COMPLETED,
            node_results=[],
        )
        mock_execution_repo.get.return_value = original

        evaluation = EvaluationResult(
            score=3.0, pass_flag=False, reason="Bad", feedback="Fix the output format",
        )

        use_case.execute(eid, evaluation)

        context = mock_execute_workflow.execute.call_args[0][1]
        assert context.parameters["refine_feedback"] == "Fix the output format"
        assert context.parameters["previous_execution_id"] == str(eid)
        assert context.parameters["qa_score"] == 3.0
        assert context.trigger_type == "handoff"


class TestThresholdConstants:
    def test_pass_threshold_is_8(self):
        assert PASS_THRESHOLD == 8.0

    def test_max_attempts_is_3(self):
        assert MAX_REFINE_ATTEMPTS == 3
