from __future__ import annotations

from enum import Enum

from common_schemas.exceptions import ValidationError


class SkillState(str, Enum):
    DRAFT = "draft"
    REVIEW = "review"
    APPROVED = "approved"
    PUBLISHED = "published"
    ARCHIVED = "archived"


_TRANSITIONS: dict[SkillState, list[SkillState]] = {
    SkillState.DRAFT: [SkillState.REVIEW],
    SkillState.REVIEW: [SkillState.APPROVED, SkillState.DRAFT],
    SkillState.APPROVED: [SkillState.PUBLISHED, SkillState.DRAFT],
    SkillState.PUBLISHED: [SkillState.ARCHIVED],
    SkillState.ARCHIVED: [SkillState.DRAFT],
}


class SkillLifecycle:
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
