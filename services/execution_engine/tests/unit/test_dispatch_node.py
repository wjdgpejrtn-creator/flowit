"""DispatchNodeUseCase 단위 테스트 — 실행, 재시도.

credential 주입은 ADR-0018 Phase 2b에서 CatalogNodeExecutor로 이동 —
관련 테스트는 test_catalog_node_executor.py 참조.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from common_schemas.enums import RiskLevel
from common_schemas.workflow import NodeConfig, NodeInstance, Position
from src.application.use_cases.dispatch_node import DispatchNodeUseCase
from src.domain.entities.retry_policy import RetryPolicy
from src.domain.services.retry_manager import RetryManager


def _make_node(credential_id=None):
    return NodeInstance(
        instance_id=uuid4(),
        node_id=uuid4(),
        parameters={"key": "value"},
        credential_id=credential_id,
        position=Position(x=0, y=0),
    )


def _make_config():
    return NodeConfig(
        node_id=uuid4(),
        node_type="http_request",
        name="HTTP Request",
        category="external",
        version="1.0.0",
        input_schema={},
        output_schema={},
        parameter_schema={},
        risk_level=RiskLevel.LOW,
        required_connections=[],
        description="HTTP 요청 노드",
        is_mvp=True,
    )


@pytest.fixture
def mock_executor():
    return MagicMock()


@pytest.fixture
def mock_events():
    return MagicMock()


@pytest.fixture
def use_case(mock_executor, mock_events):
    return DispatchNodeUseCase(
        node_executor=mock_executor,
        event_publisher=mock_events,
        retry_manager=RetryManager(),
        retry_policy=RetryPolicy(max_retries=2, backoff_base_seconds=0.01, retryable_errors=["TimeoutError"]),
    )


class TestDispatchNodeSuccess:
    def test_successful_execution(self, use_case, mock_executor):
        """정상 실행 → status=succeeded"""
        mock_executor.execute.return_value = {"result": "ok"}
        node = _make_node()
        config = _make_config()

        result = use_case.execute(
            node=node, config=config, inputs={"data": 1},
            user_id=uuid4(), execution_id=uuid4(),
        )

        assert result.status == "succeeded"
        assert result.output == {"result": "ok"}
        assert result.retry_count == 0
        assert result.error is None

    def test_passes_inputs_and_context_to_executor(self, use_case, mock_executor):
        """inputs는 가공 없이, NodeContext는 execution_id/user_id로 채워 executor에 전달."""
        mock_executor.execute.return_value = {}
        node = _make_node(credential_id=uuid4())
        config = _make_config()
        user_id = uuid4()
        execution_id = uuid4()

        use_case.execute(
            node=node, config=config, inputs={"x": 1},
            user_id=user_id, execution_id=execution_id,
        )

        passed_node, passed_config, passed_inputs, passed_context = (
            mock_executor.execute.call_args[0]
        )
        assert passed_inputs == {"x": 1}
        assert passed_context.execution_id == execution_id
        assert passed_context.user_id == user_id


class TestDispatchNodeRetry:
    @patch("time.sleep")
    def test_retries_on_timeout(self, mock_sleep, use_case, mock_executor):
        """TimeoutError → 재시도 후 성공"""
        mock_executor.execute.side_effect = [
            TimeoutError("timeout"),
            {"result": "ok"},
        ]
        node = _make_node()
        config = _make_config()

        result = use_case.execute(
            node=node, config=config, inputs={},
            user_id=uuid4(), execution_id=uuid4(),
        )

        assert result.status == "succeeded"
        assert result.retry_count == 1
        mock_sleep.assert_called_once()

    @patch("time.sleep")
    def test_max_retries_exhausted(self, mock_sleep, use_case, mock_executor):
        """max_retries 초과 → status=failed"""
        mock_executor.execute.side_effect = TimeoutError("timeout")
        node = _make_node()
        config = _make_config()

        result = use_case.execute(
            node=node, config=config, inputs={},
            user_id=uuid4(), execution_id=uuid4(),
        )

        assert result.status == "failed"
        assert result.retry_count == 2
        assert "timeout" in result.error

    def test_non_retryable_error_fails_immediately(self, use_case, mock_executor):
        """non-retryable 에러 → 즉시 실패, 재시도 0"""
        mock_executor.execute.side_effect = PermissionError("denied")
        node = _make_node()
        config = _make_config()

        result = use_case.execute(
            node=node, config=config, inputs={},
            user_id=uuid4(), execution_id=uuid4(),
        )

        assert result.status == "failed"
        assert result.retry_count == 0
        assert "denied" in result.error
