from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from ..entities.marketplace_company_skill import MarketplaceCompanySkill
from ..entities.marketplace_personal_skill import MarketplacePersonalSkill
from ..entities.marketplace_team_skill import MarketplaceTeamSkill
from ..value_objects.skill_scope import SkillScope


class SkillRepository(ABC):
    """Skills Marketplace 3계층 스킬 저장소 인터페이스 (Port).

    Port 정의는 skills_marketplace(소비 모듈)가 소유하고, 구현체는 `storage/repositories/`가
    제공한다 (auth/nodes_graph 일반 패턴 정합 — ADR-0017 + 5/20 박아름·조장 합의).
    CLAUDE.md L146(storage 소유)은 본 결정으로 정정됨.

    NOTE: 메서드 시그니처는 깊이 1(뼈대) 기준. 실제 쿼리/제약은 PR-2d 구현 + PR-2e DDL 시 확정.
    하이브리드 검색(`search`)은 BGE-M3 embedding 코사인 유사도 + 키워드(TSVECTOR) 결합 예정.
    """

    @abstractmethod
    async def save_personal(self, skill: MarketplacePersonalSkill) -> MarketplacePersonalSkill:
        """개인 스킬 생성/갱신 (upsert)."""
        ...

    @abstractmethod
    async def save_team(self, skill: MarketplaceTeamSkill) -> MarketplaceTeamSkill:
        """팀 스킬 생성/갱신 (승격 결과 저장)."""
        ...

    @abstractmethod
    async def save_company(self, skill: MarketplaceCompanySkill) -> MarketplaceCompanySkill:
        """전사 스킬 생성/갱신 (승격 결과 저장)."""
        ...

    @abstractmethod
    async def get_personal(self, skill_id: UUID) -> MarketplacePersonalSkill | None:
        """개인 스킬 단일 조회."""
        ...

    @abstractmethod
    async def get_team(self, skill_id: UUID) -> MarketplaceTeamSkill | None:
        """팀 스킬 단일 조회."""
        ...

    @abstractmethod
    async def get_company(self, skill_id: UUID) -> MarketplaceCompanySkill | None:
        """전사 스킬 단일 조회."""
        ...

    @abstractmethod
    async def search(
        self,
        query_embedding: list[float],
        scope: SkillScope,
        limit: int = 10,
        include_promoted: bool = False,
    ) -> list[MarketplacePersonalSkill | MarketplaceTeamSkill | MarketplaceCompanySkill]:
        """하이브리드 검색 — scope 범위 내 embedding 유사도 top-k.

        ai_agent Workflow Composer가 사용자 의도(intent)와 유사한 스킬 후보를 옵션 제시할 때 호출
        (CLAUDE.md L148, ADR-0017 §Composer 검색 흐름).

        include_promoted=False(기본): 상위 scope로 승격 완료된 원본(`promoted_to_*` 존재)은
        검색 결과에서 제외 — 같은 스킬이 personal+team 중복 노출되는 것을 방지 (승격=복제 정책,
        조장 리뷰 #98). 실제 WHERE 필터(`promoted_to_* IS NULL`)는 storage 구현 시 적용.
        """
        ...
