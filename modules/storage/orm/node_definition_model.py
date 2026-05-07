from __future__ import annotations

import uuid
from typing import Any, Optional

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, Index, String, Text
from sqlalchemy.dialects import postgresql as pg
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class NodeDefinitionModel(Base):
    __tablename__ = "node_definitions"

    node_id: Mapped[uuid.UUID] = mapped_column(pg.UUID(as_uuid=True), primary_key=True)
    node_type: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(20), nullable=False)
    input_schema: Mapped[dict[str, Any]] = mapped_column(pg.JSONB, nullable=False)
    output_schema: Mapped[dict[str, Any]] = mapped_column(pg.JSONB, nullable=False)
    parameter_schema: Mapped[dict[str, Any]] = mapped_column(pg.JSONB, nullable=False)
    risk_level: Mapped[str] = mapped_column(String(20), nullable=False)
    required_connections: Mapped[list[str]] = mapped_column(pg.ARRAY(String), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    is_mvp: Mapped[bool] = mapped_column(Boolean, default=False)
    service_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    embedding: Mapped[Optional[list[float]]] = mapped_column(Vector(768), nullable=True)

    __table_args__ = (
        Index("ix_node_definitions_embedding_hnsw", "embedding", postgresql_using="hnsw", postgresql_ops={"embedding": "vector_cosine_ops"}),
    )
