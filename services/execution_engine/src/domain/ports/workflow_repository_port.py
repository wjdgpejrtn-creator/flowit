from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from common_schemas.workflow import NodeConfig, WorkflowSchema


class WorkflowRepositoryPort(ABC):

    @abstractmethod
    def get(self, workflow_id: UUID) -> WorkflowSchema:
        ...

    @abstractmethod
    def get_node_config(self, node_id: UUID) -> NodeConfig:
        ...
