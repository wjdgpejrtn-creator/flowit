"""HandleHandoffUseCase 단위 테스트 — 핸드오프 수신 → 워크플로우 실행 위임."""
from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from common_schemas.enums import ExecutionStatus
from common_schemas.exceptions import ValidationError
from common_schemas.handoff import HandoffPayload

from src.application.use_cases.handle_handoff import HandleHandoffUseCase
from src.domain.entities.execution_result import ExecutionResult


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
def use_case(mock_workflow_repo, mock_execute_workflow):
    return HandleHandoffUseCase(
        workflow_repo=mock_workflow_repo,
        execute_workflow=mock_execute_workflow,
    )


class TestHandleHandoff:
    def test_forward_handoff_delegates_to_execute(self, use_case, mock_execute_workflow):
        wid = uuid4()
        uid = uuid4()
        payload = HandoffPayload(
            handoff_type="result_review",
            direction="forward",
            error_codes=[],
            error_messages=[],
            state_data={"workflow_id": str(wid), "user_id": str(uid)},
            correlation_id=uuid4(),
        )

        result = use_case.execute(payload)

        assert result.status == ExecutionStatus.COMPLETED
        mock_execute_workflow.execute.assert_called_once()
        call_args = mock_execute_workflow.execute.call_args
        assert call_args[0][0] == wid

    def test_context_trigger_type_is_handoff(self, use_case, mock_execute_workflow):
        payload = HandoffPayload(
            handoff_type="result_review",
            direction="forward",
            error_codes=[],
            error_messages=[],
            state_data={
                "workflow_id": str(uuid4()),
                "user_id": str(uuid4()),
            },
            correlation_id=uuid4(),
        )

        use_case.execute(payload)

        context = mock_execute_workflow.execute.call_args[0][1]
        assert context.trigger_type == "handoff"

    def test_missing_workflow_id_raises(self, use_case):
        payload = HandoffPayload(
            handoff_type="result_review",
            direction="forward",
            error_codes=[],
            error_messages=[],
            state_data={"user_id": str(uuid4())},
            correlation_id=uuid4(),
        )

        with pytest.raises(ValidationError, match="workflow_id"):
            use_case.execute(payload)

    def test_missing_user_id_raises(self, use_case):
        payload = HandoffPayload(
            handoff_type="result_review",
            direction="forward",
            error_codes=[],
            error_messages=[],
            state_data={"workflow_id": str(uuid4())},
            correlation_id=uuid4(),
        )

        with pytest.raises(ValidationError, match="user_id"):
            use_case.execute(payload)

    def test_parameters_passed_through(self, use_case, mock_execute_workflow):
        payload = HandoffPayload(
            handoff_type="result_review",
            direction="forward",
            error_codes=[],
            error_messages=[],
            state_data={
                "workflow_id": str(uuid4()),
                "user_id": str(uuid4()),
                "parameters": {"custom_key": "custom_val"},
            },
            correlation_id=uuid4(),
        )

        use_case.execute(payload)

        context = mock_execute_workflow.execute.call_args[0][1]
        assert context.parameters == {"custom_key": "custom_val"}
