from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, DateTime, Index, String, Text, func
from sqlalchemy.dialects import postgresql as pg
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class NodeDefinitionModel(Base):
    __tablename__ = "node_definitions"
    __table_args__ = (
        Index(
            "ix_node_definitions_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        Index(
            "ix_node_definitions_is_mvp",
            "is_mvp",
            postgresql_where="is_mvp = TRUE",
        ),
    )

    node_id: Mapped[uuid.UUID] = mapped_column(
        pg.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    node_type: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(20), nullable=False, server_default="1.0")
    input_schema: Mapped[dict[str, Any]] = mapped_column(pg.JSONB, nullable=False)
    output_schema: Mapped[dict[str, Any]] = mapped_column(pg.JSONB, nullable=False)
    parameter_schema: Mapped[dict[str, Any]] = mapped_column(
        pg.JSONB, nullable=False, server_default="'{}'::jsonb"
    )
    risk_level: Mapped[str] = mapped_column(String(20), nullable=False, server_default="Low")
    required_connections: Mapped[list[str]] = mapped_column(
        pg.ARRAY(String), nullable=False, server_default="{}"
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    is_mvp: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    service_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    embedding: Mapped[Optional[list[float]]] = mapped_column(Vector(768), nullable=True)
    # ADR-0020 (i) scope 격리 — NULL=company 전역(기존 53종 비침습)
    owner_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        pg.UUID(as_uuid=True), nullable=True
    )
    team_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        pg.UUID(as_uuid=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
