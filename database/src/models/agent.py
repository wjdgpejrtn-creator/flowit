from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, TimestampMixin, uuid_pk


class AgentModel(TimestampMixin, Base):
    __tablename__ = "agents"

    agent_id: Mapped[uuid.UUID] = uuid_pk("agent_id")
    name: Mapped[str] = mapped_column(String(200))
    agent_type: Mapped[str] = mapped_column(String(50))
    public_key: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), server_default="inactive")
    last_heartbeat: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    metadata_json: Mapped[dict | None] = mapped_column(
        "metadata", JSONB, server_default="'{}'::jsonb"
    )
