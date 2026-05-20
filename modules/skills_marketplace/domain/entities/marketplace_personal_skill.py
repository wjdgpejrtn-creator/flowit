from __future__ import annotations

from typing import Any
from uuid import UUID

from common_schemas.types import UtcDatetime
from pydantic import BaseModel, Field

from ..value_objects.skill_state import SkillState


class MarketplacePersonalSkill(BaseModel):
    """개인 범위 마켓플레이스 스킬 (ADR-0012 v3 3계층 중 personal).

    `ai_agent.PersonalSkill`(사용자 패턴/기억, GCS memory.md)과는 도메인이 완전히 다르다 —
    이쪽은 워크플로우 자동화 스킬 노드(NodeDefinition 메타 + SkillDocument). 이름 충돌 회피를 위해
    `Marketplace` 접두사 채택 (ADR-0012 §"skills_marketplace 측 다른 이름" + 5/20 박아름·조장 합의).

    두 lifecycle 축 (옵션 A, 5/20 합의):
    - `scope` (범위): 본 entity = personal. PromotionService로 team/company 승격
    - `lifecycle_state` (게시): SkillLifecycle로 draft → review → approved → published 전이

    산출물 이중 저장 (ADR-0017):
    - 메타데이터(본 entity) → skills_marketplace 테이블 (PostgreSQL, PR-2e DDL 확정)
    - SkillDocument(markdown) → GCS 버킷 (`skill_document_uri`)

    NOTE: 필드는 PR-2d 통합 설계 기준. 실제 컬럼/제약은 PR-2e schema 마이그레이션 시 확정.
    """

    skill_id: UUID
    owner_user_id: UUID                              # 개인 스킬 소유자 (= 작성자)
    name: str
    description: str
    node_definition_id: UUID                         # nodes_graph NodeDefinition 참조 (스킬 ↔ 노드 연결)
    lifecycle_state: SkillState = SkillState.DRAFT   # 게시 상태 (storage Skill에서 흡수)
    skill_document_uri: str | None = None            # GCS SkillDocument(markdown) 경로 (ADR-0017)
    embedding: list[float] | None = None             # BGE-M3 768d (하이브리드 검색용)
    workflow_id: UUID | None = None                  # 연결 워크플로우 (storage Skill 흡수)
    tags: list[str] = Field(default_factory=list)
    version: str = "0.1.0"
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: UtcDatetime
    updated_at: UtcDatetime
