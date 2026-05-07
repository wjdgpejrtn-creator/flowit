from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, TimestampMixin, uuid_pk


class SkillReviewModel(TimestampMixin, Base):
    __tablename__ = "skill_reviews"

    review_id: Mapped[uuid.UUID] = uuid_pk("review_id")
    skill_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("skills.skill_id", ondelete="CASCADE")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.user_id")
    )
    rating: Mapped[int] = mapped_column(Integer)
    comment: Mapped[str | None] = mapped_column(Text)


class MarketplaceRecommendationModel(Base):
    __tablename__ = "marketplace_recommendations"

    recommendation_id: Mapped[uuid.UUID] = uuid_pk("recommendation_id")
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.user_id")
    )
    skill_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("skills.skill_id", ondelete="CASCADE")
    )
    score: Mapped[float] = mapped_column(Numeric(5, 4))
    reason: Mapped[str | None] = mapped_column(String(200))
    is_dismissed: Mapped[bool] = mapped_column(server_default="false")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SkillDependencyModel(Base):
    __tablename__ = "skill_dependencies"

    skill_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("skills.skill_id", ondelete="CASCADE"),
        primary_key=True,
    )
    depends_on_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("skills.skill_id", ondelete="CASCADE"),
        primary_key=True,
    )
