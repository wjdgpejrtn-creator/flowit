from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from common_schemas.workflow import NodeConfig, NodeExecutionState, NodeInstance

from ...domain.entities.execution_result import NodeResult
from ...domain.entities.retry_policy import RetryPolicy
from ...domain.ports.credential_provider_port import CredentialProviderPort
from ...domain.ports.event_publisher_port import EventPublisherPort
from ...domain.ports.node_executor_port import NodeExecutorPort
from ...domain.services.retry_manager import RetryManager


class DispatchNodeUseCase:
    """단일 노드 실행: credential 주입 → 실행 → 재시도 → 결과 반환."""

    def __init__(
        self,
        node_executor: NodeExecutorPort,
        credential_provider: CredentialProviderPort,
        event_publisher: EventPublisherPort,
        retry_manager: RetryManager,
        retry_policy: RetryPolicy | None = None,
    ) -> None:
        self._executor = node_executor
        self._credentials = credential_provider
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
        started_at = datetime.now(timezone.utc)
        attempt = 0
        last_error: Exception | None = None

        enriched_inputs = self._inject_credentials(node, inputs, user_id)

        while True:
            try:
                output = self._executor.execute(node, config, enriched_inputs)
                return NodeResult(
                    node_instance_id=node.instance_id,
                    status="succeeded",
                    output=output,
                    started_at=started_at,
                    completed_at=datetime.now(timezone.utc),
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
            completed_at=datetime.now(timezone.utc),
            retry_count=attempt,
            error=str(last_error),
        )

    def _inject_credentials(
        self,
        node: NodeInstance,
        inputs: dict[str, Any],
        user_id: UUID,
    ) -> dict[str, Any]:
        enriched = {**inputs, "__user_id__": str(user_id)}
        if node.credential_id is None:
            return enriched
        creds = self._credentials.get_credential(node.credential_id, user_id)
        return {**enriched, "__credentials__": creds}
