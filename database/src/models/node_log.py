from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Integer, Numeric, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base


class NodeLogModel(Base):
    __tablename__ = "node_logs"
    __table_args__ = {
        "postgresql_partition_by": "RANGE (started_at)",
    }

    log_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    execution_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    node_id: Mapped[str] = mapped_column(String(100))
    node_type: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(30))
    attempt: Mapped[int] = mapped_column(Integer, server_default="1")
    input_payload: Mapped[dict | None] = mapped_column(JSONB)
    output_payload: Mapped[dict | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(Text)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    worker_id: Mapped[str | None] = mapped_column(String(100))
    started_at: Mapped[datetime] = mapped_column(
        primary_key=True, server_default=func.now()
    )
    retry_count: Mapped[int | None] = mapped_column(Integer, server_default="0")
    tool_name: Mapped[str | None] = mapped_column(String(100))
    tool_version: Mapped[str | None] = mapped_column(String(20))
    tokens_input: Mapped[int | None] = mapped_column(Integer)
    tokens_output: Mapped[int | None] = mapped_column(Integer)
    cost_usd: Mapped[float | None] = mapped_column(Numeric(10, 6))
