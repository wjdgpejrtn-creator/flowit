from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, uuid_pk


class StorageObjectModel(Base):
    __tablename__ = "storage_objects"

    object_id: Mapped[uuid.UUID] = uuid_pk("object_id")
    bucket: Mapped[str] = mapped_column(String(100))
    key: Mapped[str] = mapped_column(String(500), unique=True)
    size: Mapped[int] = mapped_column(BigInteger)
    content_type: Mapped[str] = mapped_column(String(100))
    metadata_json: Mapped[dict] = mapped_column(
        "metadata", JSONB, server_default="'{}'::jsonb"
    )
    owner_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    uploaded_at: Mapped[datetime] = mapped_column(server_default=func.now())
    expires_at: Mapped[datetime | None] = mapped_column()
