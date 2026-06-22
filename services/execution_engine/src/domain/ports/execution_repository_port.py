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
    def save_checkpoint(self, result: ExecutionResult) -> None:
        """진행 중 부분 결과(node_results)만 영속 — **status는 건드리지 않는다**.

        실행 루프가 step마다 호출한다. `save()`는 status를 무조건 덮어쓰므로(UPSERT
        EXCLUDED.status) 협조적 pause가 별도 트랜잭션으로 쓴 PAUSED를 RUNNING으로
        clobber한다. 체크포인트는 status를 보존해 pause 감지가 유실되지 않게 한다
        (ADR-0025).
        """
        ...

    @abstractmethod
    def get(self, execution_id: UUID) -> ExecutionResult:
        ...

    @abstractmethod
    def update_node_state(self, execution_id: UUID, state: NodeExecutionState) -> None:
        ...
