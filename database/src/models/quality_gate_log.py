from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, uuid_pk


class QualityGateLogModel(Base):
    __tablename__ = "quality_gate_logs"

    log_id: Mapped[uuid.UUID] = uuid_pk("log_id")
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.document_id", ondelete="CASCADE")
    )
    quality_status: Mapped[str] = mapped_column(String(30))
    metrics: Mapped[dict] = mapped_column(JSONB)
    warnings: Mapped[dict] = mapped_column(JSONB, server_default="'[]'::jsonb")
    decision_reason: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
