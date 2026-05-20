from __future__ import annotations

import asyncio
import dataclasses
import logging
from typing import Any

from common_schemas import NodeContext
from common_schemas.workflow import NodeConfig, NodeInstance

from ..domain.ports.node_executor_port import NodeExecutorPort

logger = logging.getLogger(__name__)


class CatalogNodeExecutor(NodeExecutorPort):
    """워크플로우 노드 실행 — node_type → `BaseNode.process()` 직접 호출 (ADR-0018).

    ADR-0014 경로 A(`ToolsetExecutor` 위임)를 폐기하고, 53종 노드를 동일하게
    `BaseNode.process(input, context)`로 실행한다. sync Celery worker ↔ async
    `process()` 브리지는 `asyncio.run()`으로 처리한다.
    """

    def __init__(self, node_classes: dict[str, type]) -> None:
        self._node_classes = node_classes

    def execute(
        self,
        node: NodeInstance,
        config: NodeConfig,
        inputs: dict[str, Any],
        context: NodeContext,
    ) -> dict[str, Any]:
        node_class = self._node_classes.get(config.node_type)
        if node_class is None:
            raise ValueError(f"카탈로그 미등록 node_type: {config.node_type}")

        node_instance = node_class()
        node_input = self._build_input(node_instance, node, inputs)

        logger.info(
            "CatalogNodeExecutor: node_type=%s, node=%s", config.node_type, node.instance_id
        )
        output = asyncio.run(node_instance.process(node_input, context))
        return self._to_dict(output)

    @staticmethod
    def _build_input(node_instance: Any, node: NodeInstance, inputs: dict[str, Any]) -> Any:
        """노드 parameters + 런타임 inputs를 노드의 input_schema 데이터클래스로 변환."""
        merged = {**node.parameters, **inputs}
        field_names = {f.name for f in dataclasses.fields(node_instance.input_schema)}
        kwargs = {k: v for k, v in merged.items() if k in field_names}
        return node_instance.input_schema(**kwargs)

    @staticmethod
    def _to_dict(output: Any) -> dict[str, Any]:
        """노드 output 데이터클래스를 NodeExecutorPort 계약(dict)으로 변환."""
        if dataclasses.is_dataclass(output) and not isinstance(output, type):
            return dataclasses.asdict(output)
        if isinstance(output, dict):
            return output
        return {"result": output}
