from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, Text, func
from sqlalchemy.dialects import postgresql as pg
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class _MarketplaceSkillCommon:
    """personal/team/company_skills 3계층 공통 컬럼 (ADR-0020 ②).

    SQLAlchemy 2.0 declarative mixin — `mapped_column`을 각 매핑 클래스가 복사받는다.
    `metadata`는 SQLAlchemy `DeclarativeBase.metadata`와 충돌하므로 ORM 속성명을
    `skill_metadata`로, DB 컬럼명을 `"metadata"`로 분리한다.
    """

    skill_id: Mapped[uuid.UUID] = mapped_column(
        pg.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    # ADR-0020 Q1: PUBLISHED 시점에만 채움 — 그 전엔 staging_* 컬럼이 노드 스펙 보관.
    node_definition_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        pg.UUID(as_uuid=True), ForeignKey("node_definitions.node_id"), nullable=True
    )
    lifecycle_state: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="draft"
    )
    skill_document_uri: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    embedding: Mapped[Optional[list[float]]] = mapped_column(Vector(768), nullable=True)
    # 연결 워크플로우 — workflows FK는 명세상 생략 (team_id와 동일하게 UUID만 보관)
    workflow_id: Mapped[Optional[uuid.UUID]] = mapped_column(pg.UUID(as_uuid=True), nullable=True)
    tags: Mapped[list[str]] = mapped_column(pg.JSONB, nullable=False, server_default="'[]'::jsonb")
    version: Mapped[str] = mapped_column(Text, nullable=False, server_default="0.1.0")
    skill_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", pg.JSONB, nullable=False, server_default="'{}'::jsonb"
    )
    # 노드 스펙 staging (publish 전 보관, ADR-0020 Q1 — NodeSpecStaging VO 평탄화)
    staging_category: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    staging_input_schema: Mapped[Optional[dict[str, Any]]] = mapped_column(pg.JSONB, nullable=True)
    staging_output_schema: Mapped[Optional[dict[str, Any]]] = mapped_column(pg.JSONB, nullable=True)
    staging_risk_level: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    staging_required_connections: Mapped[Optional[list[str]]] = mapped_column(pg.JSONB, nullable=True)
    staging_service_type: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class PersonalSkillModel(_MarketplaceSkillCommon, Base):
    __tablename__ = "personal_skills"

    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        pg.UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False
    )
    promoted_to_team_id: Mapped[Optional[uuid.UUID]] = mapped_column(pg.UUID(as_uuid=True), nullable=True)


class TeamSkillModel(_MarketplaceSkillCommon, Base):
    __tablename__ = "team_skills"

    # teams 테이블 부재로 FK 생략 (020_skills_marketplace_staging.sql과 정합)
    team_id: Mapped[uuid.UUID] = mapped_column(pg.UUID(as_uuid=True), nullable=False)
    author_id: Mapped[uuid.UUID] = mapped_column(
        pg.UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False
    )
    promoted_from: Mapped[Optional[uuid.UUID]] = mapped_column(pg.UUID(as_uuid=True), nullable=True)
    promoted_to_company_id: Mapped[Optional[uuid.UUID]] = mapped_column(pg.UUID(as_uuid=True), nullable=True)


class CompanySkillModel(_MarketplaceSkillCommon, Base):
    __tablename__ = "company_skills"

    author_id: Mapped[uuid.UUID] = mapped_column(
        pg.UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False
    )
    promoted_from: Mapped[Optional[uuid.UUID]] = mapped_column(pg.UUID(as_uuid=True), nullable=True)


class SkillApprovalModel(Base):
    """ADR-0020 ② — 스킬 게시 승인 감사. skill_id는 scope별 3계층 polymorphic 참조라 FK 생략."""

    __tablename__ = "skill_approvals"

    approval_id: Mapped[uuid.UUID] = mapped_column(
        pg.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    skill_id: Mapped[uuid.UUID] = mapped_column(pg.UUID(as_uuid=True), nullable=False)
    scope: Mapped[str] = mapped_column(Text, nullable=False)
    reviewer_id: Mapped[uuid.UUID] = mapped_column(
        pg.UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False
    )
    status: Mapped[str] = mapped_column(Text, nullable=False)
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
