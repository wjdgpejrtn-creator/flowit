from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, uuid_pk

if TYPE_CHECKING:
    from src.models.workflow import WorkflowModel


class ExecutionModel(Base):
    __tablename__ = "executions"

    execution_id: Mapped[uuid.UUID] = uuid_pk("execution_id")
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workflows.workflow_id")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.user_id")
    )
    status: Mapped[str] = mapped_column(String(30), server_default="pending")
    node_results: Mapped[dict] = mapped_column(JSONB, server_default="'{}'::jsonb")
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    workflow: Mapped[WorkflowModel] = relationship(back_populates="executions")
