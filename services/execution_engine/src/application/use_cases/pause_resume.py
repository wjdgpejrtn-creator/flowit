from __future__ import annotations

from typing import Any, Literal, Optional
from uuid import UUID

from common_schemas.enums import ExecutionStatus
from common_schemas.exceptions import ExecutionError

from ...domain.ports.event_publisher_port import EventPublisherPort
from ...domain.ports.execution_repository_port import ExecutionRepositoryPort


class PauseResumeUseCase:

    def __init__(
        self,
        execution_repo: ExecutionRepositoryPort,
        event_publisher: EventPublisherPort,
    ) -> None:
        self._execution_repo = execution_repo
        self._events = event_publisher

    def execute(
        self,
        execution_id: UUID,
        action: Literal["pause", "resume"],
        approval: Optional[dict[str, Any]] = None,
    ) -> None:
        result = self._execution_repo.get(execution_id)

        if action == "pause":
            self._pause(result)
        elif action == "resume":
            self._resume(result, approval)
        else:
            raise ExecutionError(f"Unknown action: {action}", code="E_INVALID_ACTION")

    def _pause(self, result) -> None:
        if result.status != ExecutionStatus.RUNNING:
            raise ExecutionError(
                f"Cannot pause execution in status={result.status.value}",
                code="E_INVALID_STATE_TRANSITION",
            )
        result.status = ExecutionStatus.PAUSED
        self._execution_repo.save(result)
        self._events.publish_status(result.execution_id, ExecutionStatus.PAUSED)

    def _resume(self, result, approval: Optional[dict[str, Any]]) -> None:
        if result.status != ExecutionStatus.PAUSED:
            raise ExecutionError(
                f"Cannot resume execution in status={result.status.value}",
                code="E_INVALID_STATE_TRANSITION",
            )
        result.status = ExecutionStatus.RUNNING
        if approval:
            result.node_results = [
                nr for nr in result.node_results
            ]
        self._execution_repo.save(result)
        self._events.publish_status(result.execution_id, ExecutionStatus.RUNNING)
