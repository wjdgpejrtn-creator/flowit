from __future__ import annotations

import logging
from typing import Any, Protocol

from common_schemas.workflow import NodeConfig, NodeInstance

from ..domain.ports.node_executor_port import NodeExecutorPort

logger = logging.getLogger(__name__)


class AgentGraphCallable(Protocol):
    def __call__(
        self,
        graph_name: str,
        inputs: dict[str, Any],
    ) -> dict[str, Any]: ...


class LangGraphDispatcher(NodeExecutorPort):

    def __init__(self, invoke_graph: AgentGraphCallable) -> None:
        self._invoke_graph = invoke_graph

    def execute(
        self,
        node: NodeInstance,
        config: NodeConfig,
        inputs: dict[str, Any],
    ) -> dict[str, Any]:
        graph_name = config.node_type
        graph_inputs = {
            "node_instance_id": str(node.instance_id),
            "parameters": node.parameters,
            **{k: v for k, v in inputs.items() if not k.startswith("__")},
        }

        logger.info(
            "LangGraphDispatcher: invoking graph=%s, node=%s",
            graph_name,
            node.instance_id,
        )
        return self._invoke_graph(graph_name=graph_name, inputs=graph_inputs)
