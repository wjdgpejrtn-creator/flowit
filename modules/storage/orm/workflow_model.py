from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.dialects import postgresql as pg
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class WorkflowModel(Base):
    __tablename__ = "workflows"

    workflow_id: Mapped[uuid.UUID] = mapped_column(pg.UUID(as_uuid=True), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    scope: Mapped[str] = mapped_column(String(10), nullable=False)
    is_draft: Mapped[bool] = mapped_column(Boolean, default=True)
    draft_spec: Mapped[Optional[dict[str, Any]]] = mapped_column(pg.JSONB, nullable=True)
    nodes: Mapped[list[dict[str, Any]]] = mapped_column(pg.JSONB, nullable=False)
    connections: Mapped[list[dict[str, Any]]] = mapped_column(pg.JSONB, nullable=False)
    version: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    sha256: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_via_session_id: Mapped[Optional[uuid.UUID]] = mapped_column(pg.UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
