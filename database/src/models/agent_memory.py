from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, uuid_pk


class AgentMemoryModel(Base):
    __tablename__ = "agent_memories"

    memory_id: Mapped[uuid.UUID] = uuid_pk("memory_id")
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.user_id")
    )
    source_session_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    memory_type: Mapped[str] = mapped_column(String(50))
    content: Mapped[str] = mapped_column(Text)
    metadata_json: Mapped[dict] = mapped_column(
        "metadata", JSONB, server_default="'{}'::jsonb"
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
