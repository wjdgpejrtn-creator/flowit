from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from celery import Celery
from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from storage.repositories.pg_execution_repository import PgExecutionRepository

from ai_agent.domain.ports.workflow_repository import WorkflowRepository
from common_schemas import PermissionSource, ValidationErrorResponse, WorkflowSchema
from common_schemas.broker_tasks import QUEUE_DEFAULT, TASK_EXECUTE_WORKFLOW
from common_schemas.enums import ExecutionStatus
from nodes_graph.application.use_cases.validate_graph_use_case import ValidateGraphUseCase

from app.dependencies.celery_client import get_celery
from app.dependencies.permission import get_permission_source
from app.dependencies.repositories import get_execution_repository, get_workflow_repository
from app.dependencies.use_cases import get_validate_graph_use_case
from app.services.workflow_service import WorkflowService

router = APIRouter(prefix="/api/v1/workflows", tags=["workflows"])


class ExecuteRequest(BaseModel):
    trigger_type: str = "manual"
    parameters: dict[str, Any] = Field(default_factory=dict)


class ExecuteResponse(BaseModel):
    execution_id: UUID
    status: str
    task_id: str


class WorkflowLatestExecutionResponse(BaseModel):
    """`/workflows/{id}` 상세 페이지 polling용 — execution + per-node status 묶음.

    `node_results`는 `update_node_state`가 채우는 list[{node_instance_id, status,
    attempt, last_error}]. canvas에서 node별 상태 표시용.
    """

    execution_id: UUID
    workflow_id: UUID
    status: ExecutionStatus
    started_at: datetime
    finished_at: datetime | None
    error: str | None
    node_states_summary: dict[str, int]
    node_results: list[dict[str, Any]]


def _service(repo: WorkflowRepository = Depends(get_workflow_repository)) -> WorkflowService:
    return WorkflowService(repo=repo)


@router.get("", response_model=list[WorkflowSchema])
async def list_workflows(
    limit: int = Query(50, ge=1, le=100, description="페이지 크기 (1-100, 기본 50)"),
    offset: int = Query(0, ge=0, description="페이지 오프셋 (0부터)"),
    permission: PermissionSource = Depends(get_permission_source),
    service: WorkflowService = Depends(_service),
) -> list[WorkflowSchema]:
    """본인 소유 워크플로우 목록 (최신 갱신순). team/public scope 가시성은 후속."""
    return await service.list_for(permission, limit=limit, offset=offset)


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


@router.get("/{workflow_id}/executions/latest", response_model=WorkflowLatestExecutionResponse | None)
async def get_latest_execution(
    workflow_id: UUID,
    permission: PermissionSource = Depends(get_permission_source),
    exec_repo: PgExecutionRepository = Depends(get_execution_repository),
) -> WorkflowLatestExecutionResponse | None:
    """워크플로우의 가장 최근 execution 1건 + per-node status 묶음 응답.

    실행 0건 = `null` 반환 (404 대신 200 + null) — frontend polling 친화.
    `/workflows/{id}` 상세 페이지가 워크플로우 정의 + 실행 상태를 동시에 표시할 때
    호출. status in (pending, running)이면 frontend가 2초 간격으로 재호출하여
    progress/canvas/timeline live 갱신.
    """
    row = await exec_repo.get_latest_by_workflow_id(workflow_id, permission.user_id)
    if row is None:
        return None
    summary = await exec_repo.get_node_states_summary(row.execution_id)
    return WorkflowLatestExecutionResponse(
        execution_id=row.execution_id,
        workflow_id=row.workflow_id,
        status=ExecutionStatus(row.status),
        started_at=row.started_at,
        finished_at=row.completed_at,
        error=row.error,
        node_states_summary=summary,
        node_results=row.node_results,
    )


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
        TASK_EXECUTE_WORKFLOW,
        args=[str(workflow_id), context_data],
        queue=QUEUE_DEFAULT,
    )
    return ExecuteResponse(execution_id=execution_id, status="queued", task_id=async_result.id)
