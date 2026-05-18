from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException

from ai_agent.domain.ports.workflow_repository import WorkflowRepository
from common_schemas import PermissionSource, ValidationErrorResponse, WorkflowSchema
from nodes_graph.application.use_cases.validate_graph_use_case import ValidateGraphUseCase

from app.dependencies.permission import get_permission_source
from app.dependencies.repositories import get_workflow_repository
from app.dependencies.use_cases import get_validate_graph_use_case
from app.services.workflow_service import WorkflowService

router = APIRouter(prefix="/api/v1/workflows", tags=["workflows"])


def _service(repo: WorkflowRepository = Depends(get_workflow_repository)) -> WorkflowService:
    return WorkflowService(repo=repo)


@router.post("", response_model=WorkflowSchema, status_code=201)
async def create_workflow(
    workflow: WorkflowSchema = Body(...),
    permission: PermissionSource = Depends(get_permission_source),
    service: WorkflowService = Depends(_service),
) -> WorkflowSchema:
    workflow_id = await service.save(workflow, permission)
    return await service.get(workflow_id)


@router.get("/{workflow_id}", response_model=WorkflowSchema)
async def get_workflow(
    workflow_id: UUID,
    _permission: PermissionSource = Depends(get_permission_source),
    service: WorkflowService = Depends(_service),
) -> WorkflowSchema:
    return await service.get(workflow_id)


@router.put("/{workflow_id}", response_model=WorkflowSchema)
async def update_workflow(
    workflow_id: UUID,
    workflow: WorkflowSchema = Body(...),
    permission: PermissionSource = Depends(get_permission_source),
    service: WorkflowService = Depends(_service),
) -> WorkflowSchema:
    if workflow.workflow_id != workflow_id:
        raise HTTPException(
            status_code=400,
            detail=f"Path workflow_id({workflow_id}) ≠ body workflow_id({workflow.workflow_id})",
        )
    saved_id = await service.save(workflow, permission)
    return await service.get(saved_id)


@router.post("/{workflow_id}/validate", response_model=ValidationErrorResponse)
async def validate_workflow(
    workflow_id: UUID,
    _permission: PermissionSource = Depends(get_permission_source),
    service: WorkflowService = Depends(_service),
    use_case: ValidateGraphUseCase = Depends(get_validate_graph_use_case),
) -> ValidationErrorResponse:
    workflow = await service.get(workflow_id)
    return await use_case.execute(workflow)
