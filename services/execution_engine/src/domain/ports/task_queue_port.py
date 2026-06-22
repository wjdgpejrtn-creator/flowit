from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Literal
from uuid import UUID


class TaskQueuePort(ABC):

    @abstractmethod
    def dispatch(self, task_name: str, args: dict[str, Any]) -> str:
        ...

    @abstractmethod
    def dispatch_chord(self, tasks: list[dict[str, Any]], callback: str) -> str:
        ...

    @abstractmethod
    def revoke(self, task_id: str, *, terminate: bool = True) -> None:
        ...

    @abstractmethod
    def dispatch_workflow(
        self,
        *,
        execution_id: UUID,
        workflow_id: UUID,
        user_id: UUID | None,
        trigger_type: Literal["manual", "scheduled", "handoff", "resume"],
        parameters: dict[str, Any] | None = None,
    ) -> str:
        """워크플로우 실행 enqueue (의미적 메서드).

        Adapter가 task_name / queue / args 직렬화를 책임진다. application 레이어는
        \"execution_engine.execute_workflow\" 같은 broker-specific 매직 문자열을
        몰라야 한다.
        """
        ...
