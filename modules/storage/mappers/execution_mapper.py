from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from ..orm.execution_model import ExecutionModel


@dataclass
class ExecutionRow:
    """Transfer-object row dataclass — modules/storage 전용.

    services/execution_engine/src/domain/entities/execution_result.py의 정식
    `ExecutionResult` Pydantic 엔티티와 필드 구성을 일치시키되, services→modules
    의존 방향 위반을 피하기 위해 storage 내부 dataclass로 보유. 이름은 의도적으로
    분리 (`ExecutionRow` ≠ 도메인 `ExecutionResult`) — grep 추적성 + 향후 표류
    방지. SSOT 통합(common_schemas 이전 or Port-Adapter 재설계)은 별도 PR."""

    execution_id: UUID
    workflow_id: UUID
    user_id: Optional[UUID] = None  # DB schema는 NOT NULL — Repository.save 시점에 필수
    status: str = "pending"
    node_results: list[dict[str, Any]] = field(default_factory=list)
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    task_queue_id: Optional[str] = None


class ExecutionMapper:
    @staticmethod
    def to_domain(orm: ExecutionModel) -> ExecutionRow:
        return ExecutionRow(
            execution_id=orm.execution_id,
            workflow_id=orm.workflow_id,
            user_id=orm.user_id,  # ORM은 NOT NULL, dataclass는 Optional
            status=orm.status,
            node_results=orm.node_results,
            started_at=orm.started_at,
            completed_at=orm.completed_at,
            error=orm.error,
            task_queue_id=orm.task_queue_id,
        )

    @staticmethod
    def to_orm(entity: ExecutionRow) -> ExecutionModel:
        if entity.user_id is None:
            raise ValueError(
                "ExecutionRow.user_id is required for DB persistence "
                "(executions.user_id NOT NULL). Set user_id before calling "
                "Repository.save()."
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
            task_queue_id=entity.task_queue_id,
        )
