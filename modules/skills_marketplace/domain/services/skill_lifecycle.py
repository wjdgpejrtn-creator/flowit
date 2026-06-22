from __future__ import annotations

from common_schemas.exceptions import ValidationError

from ..value_objects.skill_state import SkillState

_TRANSITIONS: dict[SkillState, list[SkillState]] = {
    SkillState.DRAFT: [SkillState.REVIEW],
    SkillState.REVIEW: [SkillState.APPROVED, SkillState.DRAFT],
    SkillState.APPROVED: [SkillState.PUBLISHED, SkillState.DRAFT],
    SkillState.PUBLISHED: [SkillState.ARCHIVED],
    # 보관(archive)은 게시 스킬을 마켓플레이스에서 임시로 숨기는 가역 동작이다. 복원(restore)은
    # 보관된 스킬을 원래 자리(PUBLISHED)로 되돌린다 — 프론트 보관/복원 UX 계약(skillApi
    # restorePersonalSkill: ARCHIVED→PUBLISHED)과 일치. DRAFT로의 복귀(재편집)도 함께 허용.
    SkillState.ARCHIVED: [SkillState.DRAFT, SkillState.PUBLISHED],
}


class SkillLifecycle:
    """게시 상태 전이 규칙 (순수 도메인 로직, 의존성 없음).

    storage/marketplace/domain/skill_lifecycle.py에서 이전 (ADR-0012 PR-2d).
    PromotionService(범위 승격)와 공존 — 한 스킬이 게시 상태 + 범위 둘 다 가짐 (옵션 A, 5/20 합의).
    """

    @staticmethod
    def can_transition(current: SkillState, target: SkillState) -> bool:
        return target in _TRANSITIONS.get(current, [])

    @staticmethod
    def transition(current: SkillState, target: SkillState) -> SkillState:
        if not SkillLifecycle.can_transition(current, target):
            raise ValidationError(
                f"Invalid transition: {current.value} -> {target.value}",
                code="E-SKILL-002",
            )
        return target
