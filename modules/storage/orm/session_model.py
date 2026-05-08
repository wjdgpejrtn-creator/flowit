from __future__ import annotations

import uuid
from datetime import datetime

from typing import Optional

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.dialects import postgresql as pg
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class SessionModel(Base):
    __tablename__ = "sessions"

    session_id: Mapped[uuid.UUID] = mapped_column(pg.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(pg.UUID(as_uuid=True), nullable=False, index=True)
    session_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    device_info: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
