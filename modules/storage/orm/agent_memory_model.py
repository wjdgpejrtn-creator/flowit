from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.dialects import postgresql as pg
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class AgentMemoryModel(Base):
    __tablename__ = "agent_memories"

    memory_id: Mapped[uuid.UUID] = mapped_column(pg.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(pg.UUID(as_uuid=True), nullable=False, index=True)
    source_session_id: Mapped[Optional[uuid.UUID]] = mapped_column(pg.UUID(as_uuid=True), nullable=True, index=True)
    memory_type: Mapped[str] = mapped_column(String(50), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", pg.JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
