from __future__ import annotations

from uuid import UUID

from ...domain.ports.skill_repository import SkillRepository
from ...domain.services.promotion_service import PromotionService


class PromoteToTeamUseCase:
    """개인 스킬 → 팀 스킬 승격 (ADR-0012 v3 lifecycle).

    NOTE: 깊이 1(뼈대) — 시그니처 + wiring만. 실제 승격 로직(personal 조회 →
    PromotionService 검증 → MarketplaceTeamSkill 변환 → save_team)은 PR-2d에서 구현.
    """

    def __init__(self, repo: SkillRepository) -> None:
        self._repo = repo
        self._promotion = PromotionService()

    async def execute(self, personal_skill_id: UUID, team_id: UUID) -> UUID:
        """개인 스킬을 팀 범위로 승격하고 신규 team skill_id 반환.

        PR-2d 구현 예정:
        1. repo.get_personal(personal_skill_id) → 원본 조회
        2. PromotionService.can_promote(PERSONAL, TEAM) 검증
        3. MarketplaceTeamSkill 변환 (promoted_from=personal_skill_id, team_id)
        4. repo.save_team() → 저장
        """
        raise NotImplementedError("PR-2d 구현 예정 (깊이 1 뼈대)")
