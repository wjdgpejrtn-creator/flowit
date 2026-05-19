from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from ..orm.execution_model import ExecutionModel


@dataclass
class ExecutionResult:
    """스펙 기반 임시 정의 — services/execution_engine/src/domain/entities/
    execution_result.py에 정식 entity 있으나 services→modules 의존 방향
    위반이라 import 못함. SSOT 통합은 별도 PR(common_schemas 이전 또는
    Port-Adapter 재설계)로 처리. 본 임시 dataclass는 정식 entity와 필드
    구성 일치 유지."""

    execution_id: UUID
    workflow_id: UUID
    user_id: Optional[UUID] = None  # DB schema는 NOT NULL — Repository.save 시점에 필수
    status: str = "pending"
    node_results: list[dict[str, Any]] = field(default_factory=list)
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    celery_task_id: Optional[str] = None


class ExecutionMapper:
    @staticmethod
    def to_domain(orm: ExecutionModel) -> ExecutionResult:
        return ExecutionResult(
            execution_id=orm.execution_id,
            workflow_id=orm.workflow_id,
            user_id=orm.user_id,  # ORM은 NOT NULL, dataclass는 Optional
            status=orm.status,
            node_results=orm.node_results,
            started_at=orm.started_at,
            completed_at=orm.completed_at,
            error=orm.error,
            celery_task_id=orm.celery_task_id,
        )

    @staticmethod
    def to_orm(entity: ExecutionResult) -> ExecutionModel:
        if entity.user_id is None:
            raise ValueError(
                "ExecutionResult.user_id is required for DB persistence "
                "(executions.user_id NOT NULL). Set user_id in the use case "
                "before calling Repository.save()."
            )
        return ExecutionModel(
            execution_id=entity.execution_id,
            workflow_id=entity.workflow_id,
            user_id=entity.user_id,
            status=entity.status,
            node_results=entity.node_results,
            started_at=entity.started_at,
            completed_at=entity.completed_at,
            error=entity.error,
            celery_task_id=entity.celery_task_id,
        )
