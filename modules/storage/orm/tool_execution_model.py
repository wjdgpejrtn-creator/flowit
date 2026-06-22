from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import CheckConstraint, DateTime, Integer, String, Text
from sqlalchemy.dialects import postgresql as pg
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class ToolExecutionModel(Base):
    __tablename__ = "tool_executions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('success', 'failed', 'timeout')",
            name="ck_tool_executions_status",
        ),
    )

    # 속성명은 도메인 entity(toolset.ToolExecutionRecord.execution_id)와 일치,
    # DB 컬럼명은 schema(016_storage_execution_quality.sql:tool_execution_id)와 일치.
    execution_id: Mapped[uuid.UUID] = mapped_column(
        "tool_execution_id", pg.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tool_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    input_data: Mapped[dict[str, Any]] = mapped_column(pg.JSONB, nullable=False)
    output_data: Mapped[Optional[dict[str, Any]]] = mapped_column(pg.JSONB, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    executed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
