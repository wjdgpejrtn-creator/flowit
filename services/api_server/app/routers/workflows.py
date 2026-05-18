from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from celery import Celery
from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel, Field

from ai_agent.domain.ports.workflow_repository import WorkflowRepository
from common_schemas import PermissionSource, ValidationErrorResponse, WorkflowSchema
from nodes_graph.application.use_cases.validate_graph_use_case import ValidateGraphUseCase

from app.dependencies.celery_client import get_celery
from app.dependencies.permission import get_permission_source
from app.dependencies.repositories import get_workflow_repository
from app.dependencies.use_cases import get_validate_graph_use_case
from app.services.workflow_service import WorkflowService

router = APIRouter(prefix="/api/v1/workflows", tags=["workflows"])

CELERY_TASK_NAME = "execution_engine.execute_workflow"
CELERY_QUEUE = "default"


class ExecuteRequest(BaseModel):
    trigger_type: str = "manual"
    parameters: dict[str, Any] = Field(default_factory=dict)


class ExecuteResponse(BaseModel):
    execution_id: UUID
    status: str
    task_id: str


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


@router.post("/{workflow_id}/execute", response_model=ExecuteResponse, status_code=202)
async def execute_workflow(
    workflow_id: UUID,
    req: ExecuteRequest = Body(default_factory=ExecuteRequest),
    permission: PermissionSource = Depends(get_permission_source),
    service: WorkflowService = Depends(_service),
    celery: Celery = Depends(get_celery),
) -> ExecuteResponse:
    """Celery broker 경유 dispatch (조장 확정 #3 — execution_engine import 0건).

    workflow 존재 확인 → execution_id 생성 → task name 문자열로 send_task.
    실제 실행은 execution_engine Celery worker가 처리. 본 라우터는 dispatch만.
    """
    await service.get(workflow_id)  # 미존재 시 NotFoundError → 404
    execution_id = uuid4()
    context_data = {
        "execution_id": str(execution_id),
        "workflow_id": str(workflow_id),
        "user_id": str(permission.user_id),
        "trigger_type": req.trigger_type,
        "parameters": req.parameters,
    }
    async_result = celery.send_task(
        CELERY_TASK_NAME,
        args=[str(workflow_id), context_data],
        queue=CELERY_QUEUE,
    )
    return ExecuteResponse(execution_id=execution_id, status="queued", task_id=async_result.id)
