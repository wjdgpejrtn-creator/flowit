from __future__ import annotations

import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from common_schemas.workflow import NodeConfig, NodeInstance

from ..domain.ports.node_executor_port import NodeExecutorPort

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS = 30
MAX_OUTPUT_BYTES = 1_048_576  # 1 MB


class SandboxExecutor(NodeExecutorPort):

    def __init__(self, timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS) -> None:
        self._timeout = timeout_seconds

    def execute(
        self,
        node: NodeInstance,
        config: NodeConfig,
        inputs: dict[str, Any],
    ) -> dict[str, Any]:
        code = inputs.get("code", node.parameters.get("code", ""))
        if not code:
            raise ValueError(f"Node {node.instance_id}: 'code' parameter is required for sandbox execution")

        logger.info("SandboxExecutor: running code for node=%s", node.instance_id)
        stdout, stderr, return_code = self._run_isolated(code)

        if return_code != 0:
            raise RuntimeError(
                f"Sandbox execution failed (exit code {return_code}): {stderr[:500]}"
            )

        return {
            "stdout": stdout,
            "stderr": stderr,
            "return_code": return_code,
        }

    def _run_isolated(self, code: str) -> tuple[str, str, int]:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False
        ) as tmp:
            tmp.write(code)
            tmp_path = Path(tmp.name)

        try:
            result = subprocess.run(
                ["python", str(tmp_path)],
                capture_output=True,
                text=True,
                timeout=self._timeout,
                env={},
            )
            stdout = result.stdout[:MAX_OUTPUT_BYTES]
            stderr = result.stderr[:MAX_OUTPUT_BYTES]
            return stdout, stderr, result.returncode
        except subprocess.TimeoutExpired:
            raise TimeoutError(
                f"Sandbox execution exceeded {self._timeout}s timeout"
            )
        finally:
            tmp_path.unlink(missing_ok=True)
