from __future__ import annotations

from uuid import UUID

from ai_agent.domain.ports.workflow_repository import WorkflowRepository
from common_schemas import PermissionSource, WorkflowSchema
from common_schemas.exceptions import NotFoundError


class WorkflowService:
    """워크플로우 CRUD — `WorkflowRepository`(modules/storage) 위임 + `owner_user_id` 주입.

    save 호출 직전에 `permission_source.user_id`를 `WorkflowSchema.owner_user_id`로 명시 주입
    (PR #66 v0.3.0 — `workflows.user_id NOT NULL` 방어).
    workflow-manager 모듈은 도입하지 않는다 (ADR-0012 v3 영구 결정). 본 서비스는 얇은 wrapper.
    """

    def __init__(self, repo: WorkflowRepository) -> None:
        self._repo = repo

    async def save(self, workflow: WorkflowSchema, permission: PermissionSource) -> UUID:
        with_owner = workflow.model_copy(update={"owner_user_id": permission.user_id})
        return await self._repo.save(with_owner)

    async def get(self, workflow_id: UUID) -> WorkflowSchema:
        result = await self._repo.find_by_id(workflow_id)
        if result is None:
            raise NotFoundError(f"Workflow {workflow_id} not found", code="E-WF-001")
        return result

    async def list_for(
        self,
        permission: PermissionSource,
        limit: int = 50,
        offset: int = 0,
    ) -> list[WorkflowSchema]:
        """본인 소유 워크플로우 목록(최신순). scope 기반 team/public 가시성은 별도 필요 시 추가."""
        return await self._repo.list_by_owner(
            owner_user_id=permission.user_id,
            limit=limit,
            offset=offset,
        )
