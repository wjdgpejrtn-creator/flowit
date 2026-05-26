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

    @abstractmethod
    async def list_by_owner(
        self,
        owner_user_id: UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> list[WorkflowSchema]:
        """본인 소유(`owner_user_id` 매칭) 워크플로우 목록. 최신 갱신(`updated_at DESC`) 순.

        team/public scope 가시성은 별도 메서드(`list_visible` 등)로 확장 — 본 메서드는
        "내 워크플로우" 단순 케이스만 책임지고, scope 확장은 frontend 요구 시점에 추가.
        """
        ...
