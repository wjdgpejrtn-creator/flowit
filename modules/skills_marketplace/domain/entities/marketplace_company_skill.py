from __future__ import annotations

from typing import Any
from uuid import UUID

from common_schemas.types import UtcDatetime
from pydantic import BaseModel, Field

from ..value_objects.skill_state import SkillState


class MarketplaceCompanySkill(BaseModel):
    """전사 범위 마켓플레이스 스킬 (ADR-0012 v3 3계층 중 company).

    `MarketplaceTeamSkill`에서 승격(PromoteToCompanyUseCase)되어 생성된다.
    전사 공개라 별도 소유 범위 식별자(team_id/owner_user_id) 없음.
    `promoted_from`이 원본 team skill_id를 가리킨다 (승격 추적).

    두 lifecycle 축 (옵션 A): scope=company(범위) + lifecycle_state(게시).

    NOTE: 필드는 PR-2d 통합 설계 기준. 실제 컬럼/제약은 PR-2e schema 마이그레이션 시 확정.
    """

    skill_id: UUID
    author_id: UUID                                  # 원작성자 (storage Skill 흡수)
    name: str
    description: str
    node_definition_id: UUID                         # nodes_graph NodeDefinition 참조
    lifecycle_state: SkillState = SkillState.DRAFT   # 게시 상태 (storage Skill에서 흡수)
    skill_document_uri: str | None = None            # GCS SkillDocument(markdown) 경로 (ADR-0017)
    embedding: list[float] | None = None             # BGE-M3 768d (하이브리드 검색용)
    workflow_id: UUID | None = None                  # 연결 워크플로우 (storage Skill 흡수)
    tags: list[str] = Field(default_factory=list)
    version: str = "0.1.0"
    metadata: dict[str, Any] = Field(default_factory=dict)
    promoted_from: UUID | None = None                # 원본 MarketplaceTeamSkill.skill_id (승격 추적)
    created_at: UtcDatetime
    updated_at: UtcDatetime
