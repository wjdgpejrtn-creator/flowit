from __future__ import annotations

from uuid import UUID

from ...domain.ports.skill_repository import SkillRepository
from ...domain.services.promotion_service import PromotionService


class PromoteToCompanyUseCase:
    """팀 스킬 → 전사 스킬 승격 (ADR-0012 v3 lifecycle).

    NOTE: 깊이 1(뼈대) — 시그니처 + wiring만. 실제 승격 로직(team 조회 →
    PromotionService 검증 → MarketplaceCompanySkill 변환 → save_company)은 PR-2d에서 구현.
    """

    def __init__(self, repo: SkillRepository) -> None:
        self._repo = repo
        self._promotion = PromotionService()

    async def execute(self, team_skill_id: UUID) -> UUID:
        """팀 스킬을 전사 범위로 승격하고 신규 company skill_id 반환.

        PR-2d 구현 예정:
        1. repo.get_team(team_skill_id) → 원본 조회
        2. PromotionService.can_promote(TEAM, COMPANY) 검증
        3. MarketplaceCompanySkill 변환 (promoted_from=team_skill_id)
        4. repo.save_company() → 저장
        """
        raise NotImplementedError("PR-2d 구현 예정 (깊이 1 뼈대)")
