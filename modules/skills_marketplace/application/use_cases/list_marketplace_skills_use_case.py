from __future__ import annotations

from ...domain.entities.marketplace_company_skill import MarketplaceCompanySkill
from ...domain.entities.marketplace_team_skill import MarketplaceTeamSkill
from ...domain.ports.skill_repository import SkillRepository
from ...domain.value_objects.skill_scope import SkillScope
from ...domain.value_objects.skill_state import SkillState

MarketplaceSkillResult = MarketplaceTeamSkill | MarketplaceCompanySkill


class ListMarketplaceSkillsUseCase:
    """마켓플레이스 Team/Company 탭 browse 목록 — 검색어 없이 게시 스킬 나열.

    `SearchSkillsUseCase`(embedding 유사도, Composer 후보 제시)와 별개. 마켓플레이스 UI는
    검색어 없이 게시 스킬 전체를 최신순으로 보여주므로 embedding이 불필요하다(repo.list_by_scope).

    lifecycle_state 기본 PUBLISHED(ADR-0020 (b)): 미검토 DRAFT/REVIEW를 마켓플레이스에 노출하지
    않는다. scope=PERSONAL은 owner 범위라 본 use case 대상 아님(repo가 ValueError).
    """

    def __init__(self, repo: SkillRepository) -> None:
        self._repo = repo

    async def execute(
        self,
        scope: SkillScope,
        lifecycle_state: SkillState | None = SkillState.PUBLISHED,
        limit: int = 50,
        offset: int = 0,
    ) -> list[MarketplaceSkillResult]:
        return await self._repo.list_by_scope(
            scope, lifecycle_state=lifecycle_state, limit=limit, offset=offset
        )
