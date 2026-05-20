from __future__ import annotations

from uuid import UUID

from common_schemas.types import UtcDatetime
from pydantic import BaseModel


class MarketplaceCompanySkill(BaseModel):
    """전사 범위 마켓플레이스 스킬 (ADR-0012 v3 3계층 중 company).

    `MarketplaceTeamSkill`에서 승격(PromoteToCompanyUseCase)되어 생성된다.
    전사 공개라 별도 소유 범위 식별자(team_id/owner_user_id) 없음.
    `promoted_from`이 원본 team skill_id를 가리킨다 (승격 추적).

    NOTE: 필드는 깊이 1(뼈대) 기준. 실제 컬럼/제약은 PR-2e schema 마이그레이션 시 확정.
    """

    skill_id: UUID
    name: str
    description: str
    node_definition_id: UUID                         # nodes_graph NodeDefinition 참조
    skill_document_uri: str | None = None            # GCS SkillDocument(markdown) 경로 (ADR-0017)
    embedding: list[float] | None = None             # BGE-M3 768d (하이브리드 검색용)
    promoted_from: UUID | None = None                # 원본 MarketplaceTeamSkill.skill_id (승격 추적)
    created_at: UtcDatetime
    updated_at: UtcDatetime
