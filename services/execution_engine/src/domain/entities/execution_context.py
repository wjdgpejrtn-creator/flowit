from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from common_schemas.types import UtcDatetime


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ExecutionContext(BaseModel):
    model_config = ConfigDict(frozen=True)

    execution_id: UUID
    workflow_id: UUID
    user_id: UUID
    trigger_type: Literal["manual", "scheduled", "handoff"]
    started_at: UtcDatetime = Field(default_factory=_utcnow)
    parameters: dict[str, Any] = Field(default_factory=dict)
