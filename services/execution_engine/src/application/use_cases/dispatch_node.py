from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from common_schemas import NodeContext
from common_schemas.workflow import NodeConfig, NodeInstance

from ...domain.entities.execution_result import NodeResult
from ...domain.entities.retry_policy import RetryPolicy
from ...domain.ports.event_publisher_port import EventPublisherPort
from ...domain.ports.node_executor_port import NodeExecutorPort
from ...domain.services.retry_manager import RetryManager


class DispatchNodeUseCase:
    """단일 노드 실행: 실행 → 재시도 → 결과 반환.

    credential 주입은 ADR-0018 Phase 2b에서 `CatalogNodeExecutor`로 이동했다 —
    `process()` 직전 토큰을 적재하고 직후 `wipe()`하는 lifecycle이 executor
    내부에 있어야 평문 노출 구간을 최소화할 수 있기 때문이다.
    """

    def __init__(
        self,
        node_executor: NodeExecutorPort,
        event_publisher: EventPublisherPort,
        retry_manager: RetryManager,
        retry_policy: RetryPolicy | None = None,
    ) -> None:
        self._executor = node_executor
        self._events = event_publisher
        self._retry = retry_manager
        self._policy = retry_policy or RetryPolicy()

    def execute(
        self,
        node: NodeInstance,
        config: NodeConfig,
        inputs: dict[str, Any],
        user_id: UUID,
        execution_id: UUID,
    ) -> NodeResult:
        started_at = datetime.now(UTC)
        attempt = 0
        last_error: Exception | None = None

        context = NodeContext(execution_id=execution_id, user_id=user_id)

        while True:
            try:
                output = self._executor.execute(node, config, inputs, context)
                return NodeResult(
                    node_instance_id=node.instance_id,
                    status="succeeded",
                    output=output,
                    started_at=started_at,
                    completed_at=datetime.now(UTC),
                    retry_count=attempt,
                )
            except Exception as e:
                last_error = e
                if self._retry.should_retry(e, self._policy, attempt):
                    delay = self._retry.get_backoff_delay(self._policy, attempt)
                    time.sleep(delay)
                    attempt += 1
                else:
                    break

        return NodeResult(
            node_instance_id=node.instance_id,
            status="failed",
            output={},
            started_at=started_at,
            completed_at=datetime.now(UTC),
            retry_count=attempt,
            error=str(last_error),
        )
