from __future__ import annotations

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text, func, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, TimestampMixin, uuid_pk


class SkillModel(TimestampMixin, Base):
    __tablename__ = "skills"

    skill_id: Mapped[uuid.UUID] = uuid_pk("skill_id")
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    author_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.user_id")
    )
    lifecycle_state: Mapped[str] = mapped_column(String(20), server_default="draft")
    workflow_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workflows.workflow_id")
    )
    tags: Mapped[list[str]] = mapped_column(ARRAY(String), server_default="{}")
    version: Mapped[str] = mapped_column(String(20), server_default="0.1.0")
    metadata_json: Mapped[dict] = mapped_column(
        "metadata", JSONB, server_default="'{}'::jsonb"
    )
    embedding = mapped_column(Vector(768), nullable=True)
    search_vector = mapped_column(TSVECTOR, nullable=True)


class SkillStatsModel(Base):
    __tablename__ = "skill_stats"

    skill_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("skills.skill_id", ondelete="CASCADE"),
        primary_key=True,
    )
    use_count: Mapped[int] = mapped_column(Integer, server_default="0")
    avg_rating: Mapped[float | None] = mapped_column(Numeric(3, 2), server_default="0")
    review_count: Mapped[int] = mapped_column(Integer, server_default="0")
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class SkillPromotionLogModel(Base):
    __tablename__ = "skill_promotion_logs"

    log_id: Mapped[uuid.UUID] = uuid_pk("log_id")
    skill_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("skills.skill_id", ondelete="CASCADE")
    )
    from_state: Mapped[str] = mapped_column(String(20))
    to_state: Mapped[str] = mapped_column(String(20))
    changed_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.user_id")
    )
    reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
