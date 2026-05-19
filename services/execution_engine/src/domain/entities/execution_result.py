from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID

from common_schemas.enums import ExecutionStatus
from common_schemas.types import UtcDatetime
from pydantic import BaseModel, ConfigDict, Field


def _utcnow() -> datetime:
    return datetime.now(UTC)


class NodeResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    node_instance_id: UUID
    status: Literal["succeeded", "failed", "cancelled", "skipped"]
    output: dict[str, Any] = Field(default_factory=dict)
    started_at: UtcDatetime
    completed_at: UtcDatetime
    retry_count: int = 0
    error: str | None = None


class ExecutionResult(BaseModel):
    model_config = ConfigDict(frozen=False)

    execution_id: UUID
    workflow_id: UUID
    user_id: UUID | None = None
    status: ExecutionStatus = ExecutionStatus.RUNNING
    node_results: list[NodeResult] = Field(default_factory=list)
    started_at: UtcDatetime = Field(default_factory=_utcnow)
    completed_at: UtcDatetime | None = None
    error: str | None = None
    task_queue_id: str | None = None

    def mark_completed(self) -> None:
        self.status = ExecutionStatus.COMPLETED
        self.completed_at = datetime.now(UTC)

    def mark_failed(self, error: str) -> None:
        self.status = ExecutionStatus.FAILED
        self.completed_at = datetime.now(UTC)
        self.error = error

    def mark_cancelled(self) -> None:
        self.status = ExecutionStatus.CANCELLED
        self.completed_at = datetime.now(UTC)
