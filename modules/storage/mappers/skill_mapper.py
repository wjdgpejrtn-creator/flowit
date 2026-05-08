from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from ..orm.skill_model import SkillModel


@dataclass
class Skill:
    """마켓플레이스 스킬 도메인 엔티티. marketplace/domain에서 교체 예정."""

    skill_id: UUID
    name: str
    description: str
    author_id: UUID
    lifecycle_state: str = "draft"
    workflow_id: Optional[UUID] = None
    tags: list[str] = field(default_factory=list)
    version: str = "0.1.0"
    metadata: dict[str, Any] = field(default_factory=dict)
    embedding: Optional[list[float]] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class SkillMapper:
    @staticmethod
    def to_domain(orm: SkillModel) -> Skill:
        return Skill(
            skill_id=orm.skill_id,
            name=orm.name,
            description=orm.description,
            author_id=orm.author_id,
            lifecycle_state=orm.lifecycle_state,
            workflow_id=orm.workflow_id,
            tags=list(orm.tags) if orm.tags else [],
            version=orm.version,
            metadata=orm.metadata_json,
            embedding=list(orm.embedding) if orm.embedding is not None else None,
            created_at=orm.created_at,
            updated_at=orm.updated_at,
        )

    @staticmethod
    def to_orm(entity: Skill) -> SkillModel:
        return SkillModel(
            skill_id=entity.skill_id,
            name=entity.name,
            description=entity.description,
            author_id=entity.author_id,
            lifecycle_state=entity.lifecycle_state,
            workflow_id=entity.workflow_id,
            tags=entity.tags,
            version=entity.version,
            metadata_json=entity.metadata,
            embedding=entity.embedding,
        )
