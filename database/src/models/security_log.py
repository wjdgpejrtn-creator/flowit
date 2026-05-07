from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, uuid_pk


class SecurityLogModel(Base):
    __tablename__ = "security_logs"

    log_id: Mapped[uuid.UUID] = uuid_pk("log_id")
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.user_id")
    )
    event_type: Mapped[str] = mapped_column(String(100))
    ip_address: Mapped[str | None] = mapped_column(INET)
    user_agent: Mapped[str | None] = mapped_column(Text)
    details: Mapped[dict | None] = mapped_column(JSONB, server_default="'{}'::jsonb")
    severity: Mapped[str] = mapped_column(String(20), server_default="info")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
