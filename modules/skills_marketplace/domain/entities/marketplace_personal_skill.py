from __future__ import annotations

from uuid import UUID

from common_schemas.types import UtcDatetime
from pydantic import BaseModel, Field


class MarketplacePersonalSkill(BaseModel):
    """개인 범위 마켓플레이스 스킬 (ADR-0012 v3 3계층 중 personal).

    `ai_agent.PersonalSkill`(사용자 패턴/기억, GCS memory.md)과는 도메인이 완전히 다르다 —
    이쪽은 워크플로우 자동화 스킬 노드(NodeDefinition 메타 + SkillDocument). 이름 충돌 회피를 위해
    `Marketplace` 접두사 채택 (ADR-0012 §"skills_marketplace 측 다른 이름" + 5/20 박아름·조장 합의).

    산출물 이중 저장 (ADR-0017):
    - 메타데이터(본 entity) → skills_marketplace 테이블 (PostgreSQL, PR-2e DDL 확정)
    - SkillDocument(markdown) → GCS 버킷 (`skill_document_uri`가 가리킴)

    NOTE: 필드는 깊이 1(뼈대) 기준. 실제 컬럼/제약은 PR-2e schema 마이그레이션 시 확정.
    """

    skill_id: UUID
    owner_user_id: UUID                              # 개인 스킬 소유자
    name: str
    description: str
    node_definition_id: UUID                         # nodes_graph NodeDefinition 참조 (스킬 ↔ 노드 연결)
    skill_document_uri: str | None = None            # GCS SkillDocument(markdown) 경로 (ADR-0017)
    embedding: list[float] | None = None             # BGE-M3 768d (하이브리드 검색용)
    created_at: UtcDatetime
    updated_at: UtcDatetime
