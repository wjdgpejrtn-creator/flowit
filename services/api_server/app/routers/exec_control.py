from __future__ import annotations

from uuid import UUID

from celery import Celery
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from common_schemas import PermissionSource

from app.dependencies.celery_client import get_celery
from app.dependencies.permission import get_permission_source

router = APIRouter(prefix="/api/v1/executions", tags=["exec_control"])

CANCEL_TASK = "execution_engine.cancel_execution"
RESUME_TASK = "execution_engine.resume_execution"
CELERY_QUEUE = "default"


class ControlResponse(BaseModel):
    execution_id: UUID
    action: str
    task_id: str


@router.post("/{execution_id}/cancel", response_model=ControlResponse, status_code=202)
async def cancel_execution(
    execution_id: UUID,
    _permission: PermissionSource = Depends(get_permission_source),
    celery: Celery = Depends(get_celery),
) -> ControlResponse:
    async_result = celery.send_task(CANCEL_TASK, args=[str(execution_id)], queue=CELERY_QUEUE)
    return ControlResponse(execution_id=execution_id, action="cancel", task_id=async_result.id)


@router.post("/{execution_id}/resume", response_model=ControlResponse, status_code=202)
async def resume_execution(
    execution_id: UUID,
    _permission: PermissionSource = Depends(get_permission_source),
    celery: Celery = Depends(get_celery),
) -> ControlResponse:
    async_result = celery.send_task(RESUME_TASK, args=[str(execution_id)], queue=CELERY_QUEUE)
    return ControlResponse(execution_id=execution_id, action="resume", task_id=async_result.id)
