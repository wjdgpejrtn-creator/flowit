from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from common_schemas.types import UtcDatetime
from pydantic import BaseModel, ConfigDict


class ApprovalWorkflow(BaseModel):
    model_config = ConfigDict(frozen=True)

    approval_id: UUID
    skill_id: UUID
    reviewer_id: UUID
    status: Literal["pending", "approved", "rejected"]
    comment: Optional[str] = None
    reviewed_at: Optional[UtcDatetime] = None
    created_at: UtcDatetime
