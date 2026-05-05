from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, LargeBinary, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, TimestampMixin, UUIDMixin


class OAuthConnectionModel(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "oauth_connections"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    credential_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("credentials.id")
    )
    service: Mapped[str] = mapped_column(String(50))
    access_token_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary)
    refresh_token_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary)
    token_expires_at: Mapped[datetime | None] = mapped_column()
    scopes: Mapped[dict | None] = mapped_column(JSONB, server_default="'[]'::jsonb")
    is_active: Mapped[bool] = mapped_column(server_default="true")
