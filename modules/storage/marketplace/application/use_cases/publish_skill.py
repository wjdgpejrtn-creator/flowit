from __future__ import annotations

from uuid import UUID

from common_schemas.exceptions import ValidationError

from ....repositories.pg_skill_repository import PgSkillRepository
from ...domain.skill_lifecycle import SkillLifecycle, SkillState


class PublishSkillUseCase:
    def __init__(self, skill_repo: PgSkillRepository) -> None:
        self._skill_repo = skill_repo

    async def execute(self, skill_id: UUID) -> None:
        skill = await self._skill_repo.get_by_id(skill_id)
        current = SkillState(skill.lifecycle_state)
        new_state = SkillLifecycle.transition(current, SkillState.PUBLISHED)
        skill.lifecycle_state = new_state.value
        await self._skill_repo.upsert(skill)
