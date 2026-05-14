from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects import postgresql as pg
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class SkillModel(Base):
    __tablename__ = "skills"
    __table_args__ = (
        CheckConstraint(
            "lifecycle_state IN ('draft', 'pending_review', 'approved', 'rejected', 'archived')",
            name="ck_skills_lifecycle_state",
        ),
        Index("ix_skills_search_vector_gin", "search_vector", postgresql_using="gin"),
        Index(
            "ix_skills_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    skill_id: Mapped[uuid.UUID] = mapped_column(pg.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    author_id: Mapped[uuid.UUID] = mapped_column(
        pg.UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False, index=True
    )
    lifecycle_state: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="draft", index=True
    )
    workflow_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        pg.UUID(as_uuid=True), ForeignKey("workflows.workflow_id"), nullable=True
    )
    tags: Mapped[list[str]] = mapped_column(
        pg.ARRAY(String), nullable=False, server_default="{}"
    )
    version: Mapped[str] = mapped_column(String(20), nullable=False, server_default="0.1.0")
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata", pg.JSONB, nullable=False, server_default="'{}'::jsonb"
    )
    embedding: Mapped[Optional[list[float]]] = mapped_column(Vector(768), nullable=True)
    search_vector: Mapped[Optional[Any]] = mapped_column(TSVECTOR, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class SkillStatsModel(Base):
    __tablename__ = "skill_stats"

    skill_id: Mapped[uuid.UUID] = mapped_column(
        pg.UUID(as_uuid=True),
        ForeignKey("skills.skill_id", ondelete="CASCADE"),
        primary_key=True,
    )
    use_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    avg_rating: Mapped[float] = mapped_column(
        Numeric(3, 2), nullable=False, server_default="0.00"
    )
    review_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class SkillPromotionLogModel(Base):
    __tablename__ = "skill_promotion_logs"

    log_id: Mapped[uuid.UUID] = mapped_column(
        pg.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    skill_id: Mapped[uuid.UUID] = mapped_column(
        pg.UUID(as_uuid=True),
        ForeignKey("skills.skill_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    from_state: Mapped[str] = mapped_column(String(20), nullable=False)
    to_state: Mapped[str] = mapped_column(String(20), nullable=False)
    changed_by: Mapped[uuid.UUID] = mapped_column(
        pg.UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False
    )
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
