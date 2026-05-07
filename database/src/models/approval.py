from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, uuid_pk


class ApprovalModel(Base):
    __tablename__ = "approvals"

    approval_id: Mapped[uuid.UUID] = uuid_pk("approval_id")
    workflow_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workflows.workflow_id")
    )
    skill_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    requester_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.user_id")
    )
    approver_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.user_id")
    )
    status: Mapped[str] = mapped_column(String(20), server_default="pending")
    comment: Mapped[str | None] = mapped_column(Text)
    requested_at: Mapped[datetime] = mapped_column(server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column()
