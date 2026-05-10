"""ToolsetExecutor 단위 테스트 — NodeExecutorPort 구현, 입력 매핑."""
from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from common_schemas.enums import RiskLevel
from common_schemas.workflow import NodeConfig, NodeInstance, Position

from src.adapters.toolset_executor import ToolsetExecutor


def _make_node(credential_id=None):
    return NodeInstance(
        instance_id=uuid4(),
        node_id=uuid4(),
        parameters={"param1": "a", "param2": "b"},
        credential_id=credential_id,
        position=Position(x=0, y=0),
    )


def _make_config(node_type="google_sheets_read"):
    return NodeConfig(
        node_id=uuid4(),
        node_type=node_type,
        name="Google Sheets Read",
        category="external",
        version="1.0.0",
        input_schema={},
        output_schema={},
        parameter_schema={},
        risk_level=RiskLevel.MEDIUM,
        required_connections=["google"],
        description="Google Sheets 읽기",
        is_mvp=True,
    )


class TestToolsetExecutor:
    def test_executes_tool_with_correct_name(self):
        mock_fn = MagicMock(return_value={"rows": [1, 2, 3]})
        executor = ToolsetExecutor(execute_tool=mock_fn)
        node = _make_node()
        config = _make_config("google_sheets_read")

        result = executor.execute(node, config, {"extra": "data"})

        mock_fn.assert_called_once()
        call_kwargs = mock_fn.call_args[1]
        assert call_kwargs["tool_name"] == "google_sheets_read"
        assert result == {"rows": [1, 2, 3]}

    def test_merges_parameters_and_inputs(self):
        mock_fn = MagicMock(return_value={})
        executor = ToolsetExecutor(execute_tool=mock_fn)
        node = _make_node()
        config = _make_config()

        executor.execute(node, config, {"input_key": "input_val"})

        call_kwargs = mock_fn.call_args[1]
        assert call_kwargs["input_data"]["param1"] == "a"
        assert call_kwargs["input_data"]["param2"] == "b"
        assert call_kwargs["input_data"]["input_key"] == "input_val"

    def test_strips_internal_keys(self):
        mock_fn = MagicMock(return_value={})
        executor = ToolsetExecutor(execute_tool=mock_fn)
        node = _make_node()
        config = _make_config()

        executor.execute(node, config, {
            "real_data": 42,
            "__credentials__": {"api_key": "secret"},
            "__user_id__": "uid",
        })

        call_kwargs = mock_fn.call_args[1]
        assert "__credentials__" not in call_kwargs["input_data"]
        assert "__user_id__" not in call_kwargs["input_data"]
        assert call_kwargs["input_data"]["real_data"] == 42

    def test_passes_credential_id(self):
        mock_fn = MagicMock(return_value={})
        executor = ToolsetExecutor(execute_tool=mock_fn)
        cred_id = uuid4()
        node = _make_node(credential_id=cred_id)
        config = _make_config()

        executor.execute(node, config, {})

        call_kwargs = mock_fn.call_args[1]
        assert call_kwargs["credential_id"] == str(cred_id)

    def test_credential_id_none_when_no_credential(self):
        mock_fn = MagicMock(return_value={})
        executor = ToolsetExecutor(execute_tool=mock_fn)
        node = _make_node(credential_id=None)
        config = _make_config()

        executor.execute(node, config, {})

        call_kwargs = mock_fn.call_args[1]
        assert call_kwargs["credential_id"] is None

    def test_propagates_execution_error(self):
        mock_fn = MagicMock(side_effect=RuntimeError("tool failed"))
        executor = ToolsetExecutor(execute_tool=mock_fn)
        node = _make_node()
        config = _make_config()

        with pytest.raises(RuntimeError, match="tool failed"):
            executor.execute(node, config, {})
