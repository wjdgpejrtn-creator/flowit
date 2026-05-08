from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, Index, String, Text, func
from sqlalchemy.dialects import postgresql as pg
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class SkillModel(Base):
    __tablename__ = "skills"

    skill_id: Mapped[uuid.UUID] = mapped_column(pg.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    author_id: Mapped[uuid.UUID] = mapped_column(pg.UUID(as_uuid=True), nullable=False, index=True)
    lifecycle_state: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    workflow_id: Mapped[Optional[uuid.UUID]] = mapped_column(pg.UUID(as_uuid=True), nullable=True)
    tags: Mapped[list[str]] = mapped_column(pg.ARRAY(String), nullable=False, default=list)
    version: Mapped[str] = mapped_column(String(20), nullable=False, default="0.1.0")
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", pg.JSONB, nullable=False, default=dict)
    embedding: Mapped[Optional[list[float]]] = mapped_column(Vector(768), nullable=True)
    search_vector: Mapped[Optional[Any]] = mapped_column(TSVECTOR, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("ix_skills_search_vector_gin", "search_vector", postgresql_using="gin"),
        Index(
            "ix_skills_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )
