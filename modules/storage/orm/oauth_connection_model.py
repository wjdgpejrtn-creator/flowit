from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, LargeBinary, String, func
from sqlalchemy.dialects import postgresql as pg
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class OAuthConnectionModel(Base):
    __tablename__ = "oauth_connections"

    oauth_id: Mapped[uuid.UUID] = mapped_column(pg.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(pg.UUID(as_uuid=True), nullable=False, index=True)
    service: Mapped[str] = mapped_column(String(20), nullable=False)
    credential_id: Mapped[uuid.UUID] = mapped_column(pg.UUID(as_uuid=True), nullable=False, unique=True)
    access_token_encrypted: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    refresh_token_encrypted: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)
    scopes: Mapped[list[str]] = mapped_column(pg.ARRAY(String), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    connected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_refreshed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
