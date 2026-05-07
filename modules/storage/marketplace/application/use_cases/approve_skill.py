from __future__ import annotations

from uuid import UUID

from ....repositories.pg_skill_repository import PgSkillRepository
from ...domain.skill_lifecycle import SkillLifecycle, SkillState


class ApproveSkillUseCase:
    def __init__(self, skill_repo: PgSkillRepository) -> None:
        self._skill_repo = skill_repo

    async def execute(self, skill_id: UUID, reviewer_id: UUID, approved: bool, comment: str | None = None) -> None:
        skill = await self._skill_repo.get_by_id(skill_id)
        current = SkillState(skill.lifecycle_state)
        target = SkillState.APPROVED if approved else SkillState.DRAFT
        new_state = SkillLifecycle.transition(current, target)
        skill.lifecycle_state = new_state.value
        await self._skill_repo.upsert(skill)
