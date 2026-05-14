"""SandboxExecutor 단위 테스트 — 코드 실행 샌드박스."""
from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from common_schemas.enums import RiskLevel
from common_schemas.workflow import NodeConfig, NodeInstance, Position

from src.adapters.sandbox_executor import SandboxExecutor


def _make_node():
    return NodeInstance(
        instance_id=uuid4(),
        node_id=uuid4(),
        parameters={"code": "print('hello')"},
        position=Position(x=0, y=0),
    )


def _make_config():
    return NodeConfig(
        node_id=uuid4(),
        node_type="python_code",
        name="Python Code",
        category="compute",
        version="1.0.0",
        input_schema={},
        output_schema={},
        parameter_schema={},
        risk_level=RiskLevel.HIGH,
        required_connections=[],
        description="Python 코드 실행",
        is_mvp=False,
    )


class TestSandboxExecutor:
    @patch("src.adapters.sandbox_executor.subprocess.run")
    def test_successful_execution(self, mock_run):
        mock_run.return_value = MagicMock(stdout="hello\n", stderr="", returncode=0)
        executor = SandboxExecutor(timeout_seconds=10)
        node = _make_node()
        config = _make_config()

        result = executor.execute(node, config, {})

        assert result["stdout"] == "hello\n"
        assert result["return_code"] == 0

    @patch("src.adapters.sandbox_executor.subprocess.run")
    def test_failed_execution_raises(self, mock_run):
        mock_run.return_value = MagicMock(
            stdout="", stderr="NameError: undefined", returncode=1,
        )
        executor = SandboxExecutor()
        node = _make_node()
        config = _make_config()

        with pytest.raises(RuntimeError, match="exit code 1"):
            executor.execute(node, config, {})

    def test_missing_code_raises(self):
        executor = SandboxExecutor()
        node = NodeInstance(
            instance_id=uuid4(),
            node_id=uuid4(),
            parameters={},
            position=Position(x=0, y=0),
        )
        config = _make_config()

        with pytest.raises(ValueError, match="'code' parameter is required"):
            executor.execute(node, config, {})

    @patch("src.adapters.sandbox_executor.subprocess.run")
    def test_timeout_raises(self, mock_run):
        import subprocess

        mock_run.side_effect = subprocess.TimeoutExpired(cmd="python", timeout=5)
        executor = SandboxExecutor(timeout_seconds=5)
        node = _make_node()
        config = _make_config()

        with pytest.raises(TimeoutError, match="timeout"):
            executor.execute(node, config, {})

    @patch("src.adapters.sandbox_executor.subprocess.run")
    def test_code_from_inputs_overrides_parameters(self, mock_run):
        mock_run.return_value = MagicMock(stdout="from inputs\n", stderr="", returncode=0)
        executor = SandboxExecutor()
        node = _make_node()
        config = _make_config()

        result = executor.execute(node, config, {"code": "print('from inputs')"})
        assert result["stdout"] == "from inputs\n"
