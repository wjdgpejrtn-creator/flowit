from __future__ import annotations

from typing import Any

from celery import Celery, chord, group

from ..domain.ports.task_queue_port import TaskQueuePort

QUEUE_ROUTING: dict[str, str] = {
    "ai": "llm",
    "external": "external_api",
}


class CeleryAdapter(TaskQueuePort):

    def __init__(self, app: Celery) -> None:
        self._app = app

    def dispatch(self, task_name: str, args: dict[str, Any]) -> str:
        args = dict(args)
        queue = args.pop("__queue__", "default")
        result = self._app.send_task(task_name, kwargs=args, queue=queue)
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
