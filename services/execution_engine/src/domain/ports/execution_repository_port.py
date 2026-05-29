from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from common_schemas.workflow import NodeExecutionState

from ..entities.execution_result import ExecutionResult


class ExecutionRepositoryPort(ABC):

    @abstractmethod
    def save(self, result: ExecutionResult) -> None:
        ...

    @abstractmethod
    def get(self, execution_id: UUID) -> ExecutionResult:
        ...

    @abstractmethod
    def update_node_state(self, execution_id: UUID, state: NodeExecutionState) -> None:
        ...
