from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID

from common_schemas.types import UtcDatetime
from pydantic import BaseModel, ConfigDict, Field


def _utcnow() -> datetime:
    return datetime.now(UTC)


class ExecutionContext(BaseModel):
    model_config = ConfigDict(frozen=True)

    execution_id: UUID
    workflow_id: UUID
    user_id: UUID
    trigger_type: Literal["manual", "scheduled", "handoff", "resume"]
    started_at: UtcDatetime = Field(default_factory=_utcnow)
    parameters: dict[str, Any] = Field(default_factory=dict)
    task_queue_id: str | None = None
