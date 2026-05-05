from __future__ import annotations

from pgvector.sqlalchemy import Vector
from sqlalchemy import String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, TimestampMixin, UUIDMixin


class NodeDefinitionModel(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "node_definitions"

    node_type: Mapped[str] = mapped_column(String(100), unique=True)
    category: Mapped[str] = mapped_column(String(50))
    display_name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    parameters: Mapped[dict] = mapped_column(JSONB, server_default="'{}'::jsonb")
    input_schema: Mapped[dict | None] = mapped_column(JSONB)
    output_schema: Mapped[dict | None] = mapped_column(JSONB)
    embedding = mapped_column(Vector(1024), nullable=True)
    is_mvp: Mapped[bool] = mapped_column(server_default="false")
    is_active: Mapped[bool] = mapped_column(server_default="true")
    version: Mapped[str] = mapped_column(String(20), server_default="1.0")
