from __future__ import annotations

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import ForeignKey, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, TimestampMixin, UUIDMixin


class SkillModel(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "skills"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    condition: Mapped[str] = mapped_column(Text)
    action: Mapped[str] = mapped_column(Text)
    rationale: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), server_default="proposed")
    version: Mapped[str] = mapped_column(String(20), server_default="1.0")
    category: Mapped[str | None] = mapped_column(String(100))
    tags: Mapped[dict | None] = mapped_column(JSONB, server_default="'[]'::jsonb")
    industry: Mapped[str | None] = mapped_column(String(100))
    embedding = mapped_column(Vector(1024), nullable=True)
    scope: Mapped[str] = mapped_column(String(20), server_default="private")
    proposed_at: Mapped[datetime | None] = mapped_column()


class SkillStatsModel(Base):
    __tablename__ = "skill_stats"

    skill_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("skills.id", ondelete="CASCADE"),
        primary_key=True,
    )
    usage_count: Mapped[int] = mapped_column(server_default="0")
    success_count: Mapped[int] = mapped_column(server_default="0")
    avg_rating: Mapped[float | None] = mapped_column(Numeric(3, 2), server_default="0")
    last_used_at: Mapped[datetime | None] = mapped_column()


class SkillPromotionLogModel(UUIDMixin, Base):
    __tablename__ = "skill_promotion_logs"

    skill_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("skills.id", ondelete="CASCADE")
    )
    from_status: Mapped[str] = mapped_column(String(30))
    to_status: Mapped[str] = mapped_column(String(30))
    changed_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    reason: Mapped[str | None] = mapped_column(Text)
    changed_at: Mapped[datetime] = mapped_column(server_default=func.now())
