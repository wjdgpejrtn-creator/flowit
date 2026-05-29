from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from common_schemas.enums import ExecutionStatus

from ..entities.execution_result import NodeResult


class EventPublisherPort(ABC):

    @abstractmethod
    def publish_status(self, execution_id: UUID, status: ExecutionStatus) -> None:
        ...

    @abstractmethod
    def publish_node_complete(self, execution_id: UUID, node_result: NodeResult) -> None:
        ...
