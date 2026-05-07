from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, uuid_pk


class IntentLogModel(Base):
    __tablename__ = "intent_logs"

    log_id: Mapped[uuid.UUID] = uuid_pk("log_id")
    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.user_id")
    )
    user_message: Mapped[str] = mapped_column(Text)
    classified_intent: Mapped[str] = mapped_column(String(100))
    confidence: Mapped[float] = mapped_column(Numeric(4, 3))
    selected_nodes: Mapped[dict | None] = mapped_column(
        JSONB, server_default="'[]'::jsonb"
    )
    metadata_json: Mapped[dict | None] = mapped_column(
        "metadata", JSONB, server_default="'{}'::jsonb"
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
