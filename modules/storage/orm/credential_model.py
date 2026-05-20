from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, LargeBinary, String, func
from sqlalchemy.dialects import postgresql as pg
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class CredentialModel(Base):
    __tablename__ = "credentials"
    __table_args__ = (
        CheckConstraint(
            "credential_kind IN ('api_key', 'oauth_token', 'password', 'certificate', 'custom')",
            name="ck_credentials_kind",
        ),
    )

    credential_id: Mapped[uuid.UUID] = mapped_column(
        pg.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        pg.UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    credential_kind: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    encrypted_data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    credential_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", pg.JSONB, nullable=False, server_default="'{}'::jsonb"
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
