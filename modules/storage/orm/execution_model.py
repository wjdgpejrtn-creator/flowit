from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects import postgresql as pg
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class ExecutionModel(Base):
    __tablename__ = "executions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'running', 'paused', 'completed', 'failed', 'cancelled')",
            name="ck_executions_status",
        ),
    )

    execution_id: Mapped[uuid.UUID] = mapped_column(
        pg.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        pg.UUID(as_uuid=True), ForeignKey("workflows.workflow_id"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        pg.UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(30), nullable=False, server_default="pending")
    node_results: Mapped[dict[str, Any]] = mapped_column(
        pg.JSONB, nullable=False, server_default="'{}'::jsonb"
    )
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    celery_task_id: Mapped[Optional[str]] = mapped_column(String(155), nullable=True)


class NodeResultModel(Base):
    __tablename__ = "node_results"
    __table_args__ = (
        CheckConstraint(
            "status IN ('succeeded', 'failed', 'cancelled', 'skipped')",
            name="ck_node_results_status",
        ),
    )

    node_result_id: Mapped[uuid.UUID] = mapped_column(
        pg.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    execution_id: Mapped[uuid.UUID] = mapped_column(
        pg.UUID(as_uuid=True),
        ForeignKey("executions.execution_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    node_instance_id: Mapped[uuid.UUID] = mapped_column(pg.UUID(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    output: Mapped[dict[str, Any]] = mapped_column(
        pg.JSONB, nullable=False, server_default="'{}'::jsonb"
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
