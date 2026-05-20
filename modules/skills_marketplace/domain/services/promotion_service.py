from __future__ import annotations

from ..value_objects.skill_scope import SkillScope


# 승격 단방향 전이 규칙 (ADR-0012 v3): PERSONAL → TEAM → COMPANY
_PROMOTION_PATH: dict[SkillScope, SkillScope] = {
    SkillScope.PERSONAL: SkillScope.TEAM,
    SkillScope.TEAM: SkillScope.COMPANY,
}


class PromotionService:
    """스킬 승격 규칙 (순수 도메인 로직, 의존성 없음).

    승격은 PERSONAL → TEAM → COMPANY 단방향만 허용. 역방향/건너뛰기 금지.

    NOTE: 깊이 1(뼈대) — 전이 가능 여부 판정만. 실제 승격 시 entity 변환/저장은
    PromoteToTeamUseCase / PromoteToCompanyUseCase(application)가 PR-2d에서 구현.
    """

    @staticmethod
    def can_promote(current: SkillScope, target: SkillScope) -> bool:
        """current → target 승격이 허용되는지 (단방향 1단계만)."""
        return _PROMOTION_PATH.get(current) == target

    @staticmethod
    def next_scope(current: SkillScope) -> SkillScope | None:
        """다음 승격 단계 반환. COMPANY(최상위)면 None."""
        return _PROMOTION_PATH.get(current)
