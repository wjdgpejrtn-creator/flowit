from __future__ import annotations

import asyncio
import dataclasses
import logging
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from typing import Any

from common_schemas import NodeContext
from common_schemas.workflow import NodeConfig, NodeInstance

from ..domain.ports.node_executor_port import NodeExecutorPort

logger = logging.getLogger(__name__)

# container가 주입하는 credential 해결기 팩토리. 호출 시 async context manager를
# 반환하며, with 블록 안에서 `inject(credential_id, node_id) -> PlaintextCredential`을
# 노출하는 서비스(auth `CredentialInjectionService`)를 yield한다.
CredentialServiceFactory = Callable[[], AbstractAsyncContextManager[Any]]


class CatalogNodeExecutor(NodeExecutorPort):
    """워크플로우 노드 실행 — node_type → `BaseNode.process()` 직접 호출 (ADR-0018).

    ADR-0014 경로 A(`ToolsetExecutor` 위임)를 폐기하고, 53종 노드를 동일하게
    `BaseNode.process(input, context)`로 실행한다. sync Celery worker ↔ async
    `process()` 브리지는 `asyncio.run()`으로 처리한다.

    Phase 2b: `node.credential_id`가 있으면 실행 직전 `CredentialInjectionService`로
    connection 토큰을 해결해 `NodeContext.connection_token`에 적재하고, `process()`
    종료 후 평문 토큰을 `wipe()`한다 (ADR-0018 Decision 5·6).
    """

    def __init__(
        self,
        node_classes: dict[str, type],
        credential_service_factory: CredentialServiceFactory | None = None,
    ) -> None:
        self._node_classes = node_classes
        self._credential_service_factory = credential_service_factory

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
        # credential 해결(async DB)과 process()(async)를 단일 이벤트 루프로 묶는다.
        return asyncio.run(self._run(node_instance, node_input, node, context))

    async def _run(
        self,
        node_instance: Any,
        node_input: Any,
        node: NodeInstance,
        context: NodeContext,
    ) -> dict[str, Any]:
        credential: Any = None
        try:
            if node.credential_id is not None:
                credential = await self._inject(node.credential_id, node.node_id)
                context.connection_token = credential.value
            output = await node_instance.process(node_input, context)
            return self._to_dict(output)
        finally:
            # 평문 connection 토큰을 노드 실행 종료 즉시 제거 (ADR-0018 Decision 5).
            if credential is not None:
                credential.wipe()
            context.wipe()

    async def _inject(self, credential_id: Any, node_id: Any) -> Any:
        if self._credential_service_factory is None:
            raise RuntimeError(
                f"노드 {node_id}가 credential을 요구하지만 credential_service_factory가 "
                "주입되지 않았다 (container.py 배선 확인)."
            )
        async with self._credential_service_factory() as service:
            return await service.inject(credential_id, node_id)

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
