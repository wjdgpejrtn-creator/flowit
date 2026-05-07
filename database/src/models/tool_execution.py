from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, uuid_pk


class ToolExecutionModel(Base):
    __tablename__ = "tool_executions"

    tool_execution_id: Mapped[uuid.UUID] = uuid_pk("tool_execution_id")
    tool_name: Mapped[str] = mapped_column(String(100))
    input_data: Mapped[dict] = mapped_column(JSONB)
    output_data: Mapped[dict | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(20))
    duration_ms: Mapped[int] = mapped_column(Integer)
    error_message: Mapped[str | None] = mapped_column(Text)
    executed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
