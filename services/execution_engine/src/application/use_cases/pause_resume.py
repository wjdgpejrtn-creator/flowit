from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from common_schemas.enums import ExecutionStatus

from ...domain.ports.event_publisher_port import EventPublisherPort
from ...domain.ports.execution_repository_port import ExecutionRepositoryPort
from ...domain.ports.task_queue_port import TaskQueuePort
from ...domain.services.execution_orchestrator import ExecutionOrchestrator


class PauseResumeUseCase:

    def __init__(
        self,
        execution_repo: ExecutionRepositoryPort,
        event_publisher: EventPublisherPort,
        orchestrator: ExecutionOrchestrator,
        task_queue: TaskQueuePort | None = None,
    ) -> None:
        self._execution_repo = execution_repo
        self._events = event_publisher
        self._orchestrator = orchestrator
        self._task_queue = task_queue

    def execute(
        self,
        execution_id: UUID,
        action: Literal["pause", "resume", "cancel"],
        approval: dict[str, Any] | None = None,
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

        if action == "cancel":
            if self._task_queue is not None and result.task_queue_id:
                self._task_queue.revoke(result.task_queue_id, terminate=True)
            result.mark_cancelled()  # status=CANCELLED + completed_at 세팅을 한 곳에서
            self._execution_repo.save(result)
            self._events.publish_status(result.execution_id, target)
            return

        if action == "resume" and self._task_queue is not None:
            # 옛 task_id로 cancel 시도 시 이미 종료된 task에 revoke가 가서 작동 안 함.
            # 새 task_id로 갱신하여 cancel 경로가 항상 현 task를 가리키게 한다.
            # dispatch 실패 시 status도 변경되지 않아 PAUSED 유지 (호출자 재시도 가능).
            new_task_id = self._task_queue.dispatch_workflow(
                execution_id=result.execution_id,
                workflow_id=result.workflow_id,
                user_id=result.user_id,
                trigger_type="resume",
                parameters={},
            )
            result.status = target
            result.task_queue_id = new_task_id
            self._execution_repo.save(result)
            self._events.publish_status(result.execution_id, target)
            return

        # pause, 또는 resume + task_queue 미주입(unit test 경로) — 단순 status 전환
        result.status = target
        self._execution_repo.save(result)
        self._events.publish_status(result.execution_id, target)
