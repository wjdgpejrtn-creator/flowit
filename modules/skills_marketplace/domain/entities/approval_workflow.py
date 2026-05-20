from __future__ import annotations

from typing import Literal
from uuid import UUID

from common_schemas.types import UtcDatetime
from pydantic import BaseModel, ConfigDict


class ApprovalWorkflow(BaseModel):
    """스킬 게시 승인 워크플로우 항목 (storage/marketplace에서 이전 — ADR-0012 PR-2d 복사).

    팀/전사 게시 전 리뷰어 승인 추적. SkillLifecycle의 REVIEW → APPROVED 전이와 짝.
    """

    model_config = ConfigDict(frozen=True)

    approval_id: UUID
    skill_id: UUID
    reviewer_id: UUID
    status: Literal["pending", "approved", "rejected"]
    comment: str | None = None
    reviewed_at: UtcDatetime | None = None
    created_at: UtcDatetime
