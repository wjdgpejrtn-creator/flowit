from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from ..orm.execution_model import ExecutionModel


@dataclass
class ExecutionResult:
    """스펙 기반 임시 정의. execution-engine 도메인 엔티티 생성 시 교체."""

    execution_id: UUID
    workflow_id: UUID
    status: str
    node_results: list[dict[str, Any]] = field(default_factory=list)
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None
    error: Optional[str] = None


class ExecutionMapper:
    @staticmethod
    def to_domain(orm: ExecutionModel) -> ExecutionResult:
        return ExecutionResult(
            execution_id=orm.execution_id,
            workflow_id=orm.workflow_id,
            status=orm.status,
            node_results=orm.node_results,
            started_at=orm.started_at,
            completed_at=orm.completed_at,
            error=orm.error,
        )

    @staticmethod
    def to_orm(entity: ExecutionResult) -> ExecutionModel:
        return ExecutionModel(
            execution_id=entity.execution_id,
            workflow_id=entity.workflow_id,
            status=entity.status,
            node_results=entity.node_results,
            started_at=entity.started_at,
            completed_at=entity.completed_at,
            error=entity.error,
        )
