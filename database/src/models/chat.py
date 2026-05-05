from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, UUIDMixin


class ChatSessionModel(UUIDMixin, Base):
    __tablename__ = "chat_sessions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    session_hash: Mapped[str] = mapped_column(String(128))
    kind: Mapped[str] = mapped_column(String(30), server_default="chat")
    is_revoked: Mapped[bool] = mapped_column(server_default="false")
    last_activity_at: Mapped[datetime] = mapped_column(server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    messages: Mapped[list[ChatMessageModel]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )


class ChatMessageModel(UUIDMixin, Base):
    __tablename__ = "chat_messages"

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chat_sessions.id", ondelete="CASCADE")
    )
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    metadata: Mapped[dict | None] = mapped_column(JSONB, server_default="'{}'::jsonb")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    session: Mapped[ChatSessionModel] = relationship(back_populates="messages")
