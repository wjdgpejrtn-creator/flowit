from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict


class ApprovalWorkflow(BaseModel):
    model_config = ConfigDict(frozen=True)

    approval_id: UUID
    skill_id: UUID
    reviewer_id: UUID
    status: Literal["pending", "approved", "rejected"]
    comment: Optional[str] = None
    reviewed_at: Optional[AwareDatetime] = None
    created_at: AwareDatetime
