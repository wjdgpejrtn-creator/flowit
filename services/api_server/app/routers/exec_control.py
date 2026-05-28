from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from celery import Celery
from common_schemas import PermissionSource
from common_schemas.broker_tasks import QUEUE_DEFAULT, TASK_CANCEL_EXECUTION, TASK_RESUME_EXECUTION
from common_schemas.enums import ExecutionStatus
from common_schemas.exceptions import NotFoundError
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from storage.repositories.pg_execution_repository import PgExecutionRepository

from app.dependencies.celery_client import get_celery
from app.dependencies.permission import get_permission_source
from app.dependencies.repositories import get_execution_repository

router = APIRouter(prefix="/api/v1/executions", tags=["exec_control"])


class ControlResponse(BaseModel):
    execution_id: UUID
    action: str
    task_id: str


class ExecutionGetResponse(BaseModel):
    """폴링용 execution 조회 응답. last_event/outputs는 후속 PR에서 채움."""

    execution_id: UUID
    workflow_id: UUID
    status: ExecutionStatus
    started_at: datetime
    finished_at: datetime | None
    error: str | None
    node_states_summary: dict[str, int]
    last_event: dict[str, Any] | None = None
    outputs: dict[str, Any] | None = None


@router.get("/{execution_id}", response_model=ExecutionGetResponse)
async def get_execution(
    execution_id: UUID,
    permission: PermissionSource = Depends(get_permission_source),
    repo: PgExecutionRepository = Depends(get_execution_repository),
) -> ExecutionGetResponse:
    """Execution 단건 조회 (폴링용). 본인 소유만 200, 타인 소유 403, 미존재 404."""
    try:
        row = await repo.get(execution_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if row.user_id != permission.user_id:
        raise HTTPException(status_code=403, detail="Execution belongs to another user")
    summary = await repo.get_node_states_summary(execution_id)
    return ExecutionGetResponse(
        execution_id=row.execution_id,
        workflow_id=row.workflow_id,
        status=ExecutionStatus(row.status),
        started_at=row.started_at,
        finished_at=row.completed_at,
        error=row.error,
        node_states_summary=summary,
    )


async def _verify_execution_owner(
    execution_id: UUID,
    permission: PermissionSource,
    repo: PgExecutionRepository,
) -> None:
    """Cancel/resume 진입 직전 소유자 확인. 미존재 404, 타인 소유 403."""
    try:
        row = await repo.get(execution_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if row.user_id != permission.user_id:
        raise HTTPException(status_code=403, detail="Execution belongs to another user")


@router.post("/{execution_id}/cancel", response_model=ControlResponse, status_code=202)
async def cancel_execution(
    execution_id: UUID,
    permission: PermissionSource = Depends(get_permission_source),
    repo: PgExecutionRepository = Depends(get_execution_repository),
    celery: Celery = Depends(get_celery),
) -> ControlResponse:
    await _verify_execution_owner(execution_id, permission, repo)
    async_result = celery.send_task(TASK_CANCEL_EXECUTION, args=[str(execution_id)], queue=QUEUE_DEFAULT)
    return ControlResponse(execution_id=execution_id, action="cancel", task_id=async_result.id)


@router.post("/{execution_id}/resume", response_model=ControlResponse, status_code=202)
async def resume_execution(
    execution_id: UUID,
    permission: PermissionSource = Depends(get_permission_source),
    repo: PgExecutionRepository = Depends(get_execution_repository),
    celery: Celery = Depends(get_celery),
) -> ControlResponse:
    await _verify_execution_owner(execution_id, permission, repo)
    async_result = celery.send_task(TASK_RESUME_EXECUTION, args=[str(execution_id)], queue=QUEUE_DEFAULT)
    return ControlResponse(execution_id=execution_id, action="resume", task_id=async_result.id)
