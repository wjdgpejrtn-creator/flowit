from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class TaskQueuePort(ABC):

    @abstractmethod
    def dispatch(self, task_name: str, args: dict[str, Any]) -> str:
        ...

    @abstractmethod
    def dispatch_chord(self, tasks: list[dict[str, Any]], callback: str) -> str:
        ...
