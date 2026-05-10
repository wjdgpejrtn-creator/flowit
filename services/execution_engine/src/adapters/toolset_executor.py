from __future__ import annotations

import logging
from typing import Any, Protocol

from common_schemas.workflow import NodeConfig, NodeInstance

from ..domain.ports.node_executor_port import NodeExecutorPort

logger = logging.getLogger(__name__)


class ToolExecuteCallable(Protocol):
    def __call__(
        self,
        tool_name: str,
        input_data: dict[str, Any],
        credential_id: str | None = None,
        credentials: dict[str, str] | None = None,
        user_id: str | None = None,
    ) -> dict[str, Any]: ...


class ToolsetExecutor(NodeExecutorPort):

    def __init__(self, execute_tool: ToolExecuteCallable) -> None:
        self._execute_tool = execute_tool

    def execute(
        self,
        node: NodeInstance,
        config: NodeConfig,
        inputs: dict[str, Any],
    ) -> dict[str, Any]:
        tool_name = config.node_type
        user_id = inputs.get("__user_id__")
        credentials = inputs.get("__credentials__")

        input_data = {
            k: v for k, v in {**node.parameters, **inputs}.items()
            if not k.startswith("__")
        }

        credential_id = str(node.credential_id) if node.credential_id else None

        logger.info("ToolsetExecutor: executing tool=%s, node=%s", tool_name, node.instance_id)
        return self._execute_tool(
            tool_name=tool_name,
            input_data=input_data,
            credential_id=credential_id,
            credentials=credentials,
            user_id=user_id,
        )
