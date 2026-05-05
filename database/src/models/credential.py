from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, LargeBinary, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, TimestampMixin, UUIDMixin


class CredentialModel(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "credentials"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    name: Mapped[str] = mapped_column(String(200))
    credential_kind: Mapped[str] = mapped_column(String(50))
    encrypted_data: Mapped[bytes] = mapped_column(LargeBinary)
    metadata: Mapped[dict | None] = mapped_column(JSONB, server_default="'{}'::jsonb")
    is_active: Mapped[bool] = mapped_column(server_default="true")
