from __future__ import annotations

from typing import Any, Literal, Optional
from uuid import UUID

from common_schemas.enums import ExecutionStatus

from ...domain.ports.event_publisher_port import EventPublisherPort
from ...domain.ports.execution_repository_port import ExecutionRepositoryPort
from ...domain.ports.task_queue_port import TaskQueuePort
from ...domain.services.execution_orchestrator import ExecutionOrchestrator

EXECUTE_WORKFLOW_TASK = "execution_engine.execute_workflow"


class PauseResumeUseCase:

    def __init__(
        self,
        execution_repo: ExecutionRepositoryPort,
        event_publisher: EventPublisherPort,
        orchestrator: ExecutionOrchestrator,
        task_queue: Optional[TaskQueuePort] = None,
    ) -> None:
        self._execution_repo = execution_repo
        self._events = event_publisher
        self._orchestrator = orchestrator
        self._task_queue = task_queue

    def execute(
        self,
        execution_id: UUID,
        action: Literal["pause", "resume", "cancel"],
        approval: Optional[dict[str, Any]] = None,
    ) -> None:
        result = self._execution_repo.get(execution_id)

        if action == "pause":
            target = ExecutionStatus.PAUSED
        elif action == "resume":
            target = ExecutionStatus.RUNNING
        elif action == "cancel":
            target = ExecutionStatus.CANCELLED
        else:
            raise ValueError(f"Unknown action: {action!r}")

        self._orchestrator.validate_state_transition(result.status, target)
        result.status = target

        if action == "cancel":
            result.mark_cancelled()
            if self._task_queue is not None and result.celery_task_id:
                self._task_queue.revoke(result.celery_task_id, terminate=True)

        self._execution_repo.save(result)
        self._events.publish_status(result.execution_id, target)

        if action == "resume" and self._task_queue is not None:
            self._task_queue.dispatch(
                EXECUTE_WORKFLOW_TASK,
                args={
                    "workflow_id": str(result.workflow_id),
                    "context_data": {
                        "execution_id": str(result.execution_id),
                        "workflow_id": str(result.workflow_id),
                        "user_id": str(result.user_id) if result.user_id else None,
                        "trigger_type": "resume",
                        "parameters": {},
                    },
                    "__queue__": "default",
                },
            )
