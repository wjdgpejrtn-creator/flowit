from __future__ import annotations

from typing import Any, Literal, Optional
from uuid import UUID

from common_schemas.enums import ExecutionStatus

from ...domain.ports.event_publisher_port import EventPublisherPort
from ...domain.ports.execution_repository_port import ExecutionRepositoryPort
from ...domain.services.execution_orchestrator import ExecutionOrchestrator


class PauseResumeUseCase:

    def __init__(
        self,
        execution_repo: ExecutionRepositoryPort,
        event_publisher: EventPublisherPort,
        orchestrator: ExecutionOrchestrator,
    ) -> None:
        self._execution_repo = execution_repo
        self._events = event_publisher
        self._orchestrator = orchestrator

    def execute(
        self,
        execution_id: UUID,
        action: Literal["pause", "resume"],
        approval: Optional[dict[str, Any]] = None,
    ) -> None:
        result = self._execution_repo.get(execution_id)

        if action == "pause":
            target = ExecutionStatus.PAUSED
        else:
            target = ExecutionStatus.RUNNING

        self._orchestrator.validate_state_transition(result.status, target)
        result.status = target
        self._execution_repo.save(result)
        self._events.publish_status(result.execution_id, target)
