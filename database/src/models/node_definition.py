from __future__ import annotations

import uuid

from pgvector.sqlalchemy import Vector
from sqlalchemy import String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, TimestampMixin, uuid_pk


class NodeDefinitionModel(TimestampMixin, Base):
    __tablename__ = "node_definitions"

    node_id: Mapped[uuid.UUID] = uuid_pk("node_id")
    node_type: Mapped[str] = mapped_column(String(100), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(50))
    version: Mapped[str] = mapped_column(String(20), server_default="1.0")
    input_schema: Mapped[dict | None] = mapped_column(JSONB)
    output_schema: Mapped[dict | None] = mapped_column(JSONB)
    parameter_schema: Mapped[dict] = mapped_column(JSONB, server_default="'{}'::jsonb")
    risk_level: Mapped[str] = mapped_column(String(20), server_default="Low")
    required_connections: Mapped[list[str]] = mapped_column(
        ARRAY(String), server_default="{}"
    )
    description: Mapped[str | None] = mapped_column(Text)
    is_mvp: Mapped[bool] = mapped_column(server_default="false")
    service_type: Mapped[str | None] = mapped_column(String(50))
    embedding = mapped_column(Vector(768), nullable=True)
