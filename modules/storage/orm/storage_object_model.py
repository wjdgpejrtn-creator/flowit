from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import BigInteger, DateTime, String, func
from sqlalchemy.dialects import postgresql as pg
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class StorageObjectModel(Base):
    __tablename__ = "storage_objects"

    object_id: Mapped[uuid.UUID] = mapped_column(pg.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    bucket: Mapped[str] = mapped_column(String(100), nullable=False)
    key: Mapped[str] = mapped_column(String(500), nullable=False, unique=True)
    size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", pg.JSONB, nullable=False, default=dict)
    owner_id: Mapped[Optional[uuid.UUID]] = mapped_column(pg.UUID(as_uuid=True), nullable=True, index=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
