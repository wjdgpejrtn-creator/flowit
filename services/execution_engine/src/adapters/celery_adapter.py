from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from celery import Celery, chord, group

from ..domain.ports.task_queue_port import TaskQueuePort

QUEUE_ROUTING: dict[str, str] = {
    "ai": "llm",
    "external": "external_api",
}

# adapter 내부에 격리된 broker-specific 식별자 (CLAUDE.md application 레이어에 누설 금지)
EXECUTE_WORKFLOW_TASK_NAME = "execution_engine.execute_workflow"
DEFAULT_QUEUE = "default"


class CeleryAdapter(TaskQueuePort):

    def __init__(self, app: Celery) -> None:
        self._app = app

    def dispatch(self, task_name: str, args: dict[str, Any]) -> str:
        args = dict(args)
        queue = args.pop("__queue__", DEFAULT_QUEUE)
        result = self._app.send_task(task_name, kwargs=args, queue=queue)
        return result.id

    def dispatch_workflow(
        self,
        *,
        execution_id: UUID,
        workflow_id: UUID,
        user_id: UUID | None,
        trigger_type: Literal["manual", "scheduled", "handoff", "resume"],
        parameters: dict[str, Any] | None = None,
    ) -> str:
        context_data = {
            "execution_id": str(execution_id),
            "workflow_id": str(workflow_id),
            "user_id": str(user_id) if user_id else None,
            "trigger_type": trigger_type,
            "parameters": parameters or {},
        }
        result = self._app.send_task(
            EXECUTE_WORKFLOW_TASK_NAME,
            args=[str(workflow_id), context_data],
            queue=DEFAULT_QUEUE,
        )
        return result.id

    def dispatch_chord(self, tasks: list[dict[str, Any]], callback: str) -> str:
        sigs = []
        for t in tasks:
            task_args = dict(t.get("args", {}))
            queue = task_args.pop("__queue__", "default")
            sig = self._app.signature(t["task_name"], kwargs=task_args, queue=queue)
            sigs.append(sig)

        callback_sig = self._app.signature(callback)
        result = chord(group(sigs))(callback_sig)
        return result.id

    def revoke(self, task_id: str, *, terminate: bool = True) -> None:
        self._app.control.revoke(task_id, terminate=terminate, signal="SIGTERM")

    @staticmethod
    def resolve_queue(category: str) -> str:
        return QUEUE_ROUTING.get(category, "default")
