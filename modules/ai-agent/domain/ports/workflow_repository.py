from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional
from uuid import UUID

from common_schemas import WorkflowSchema


class WorkflowRepository(ABC):
    @abstractmethod
    async def save(self, workflow: WorkflowSchema) -> UUID: ...

    @abstractmethod
    async def find_by_id(self, workflow_id: UUID) -> Optional[WorkflowSchema]: ...
