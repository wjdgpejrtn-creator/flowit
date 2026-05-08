from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, TimestampMixin, uuid_pk


class WebhookRegistryModel(TimestampMixin, Base):
    __tablename__ = "webhook_registry"

    webhook_id: Mapped[uuid.UUID] = uuid_pk("webhook_id")
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.user_id")
    )
    name: Mapped[str] = mapped_column(String(200))
    url: Mapped[str] = mapped_column(Text)
    secret_hash: Mapped[str | None] = mapped_column(String(128))
    events: Mapped[list[str]] = mapped_column(ARRAY(String), server_default="{}")
    is_active: Mapped[bool] = mapped_column(server_default="true")
