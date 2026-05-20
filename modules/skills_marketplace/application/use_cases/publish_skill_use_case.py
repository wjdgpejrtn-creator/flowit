from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from common_schemas.exceptions import NotFoundError

from ...domain.ports.skill_repository import SkillRepository
from ...domain.services.skill_lifecycle import SkillLifecycle, SkillState
from ...domain.value_objects.skill_scope import SkillScope


class PublishSkillUseCase:
    """스킬 게시 — APPROVED → PUBLISHED.

    storage/marketplace/application/use_cases/publish_skill.py에서 이전 (ADR-0012 PR-2d).
    정석 정정: 원본 `PgSkillRepository`(구현체) 직접 의존 → `SkillRepository`(ABC) 의존.
    """

    def __init__(self, repo: SkillRepository) -> None:
        self._repo = repo

    async def execute(self, skill_id: UUID, scope: SkillScope) -> None:
        skill = await self._get(skill_id, scope)
        if skill is None:
            raise NotFoundError(f"Skill {skill_id} (scope={scope.value}) not found")

        new_state = SkillLifecycle.transition(SkillState(skill.lifecycle_state), SkillState.PUBLISHED)
        updated = skill.model_copy(update={"lifecycle_state": new_state, "updated_at": datetime.now(UTC)})
        await self._save(updated, scope)

    async def _get(self, skill_id: UUID, scope: SkillScope):
        if scope == SkillScope.PERSONAL:
            return await self._repo.get_personal(skill_id)
        if scope == SkillScope.TEAM:
            return await self._repo.get_team(skill_id)
        return await self._repo.get_company(skill_id)

    async def _save(self, skill, scope: SkillScope) -> None:
        if scope == SkillScope.PERSONAL:
            await self._repo.save_personal(skill)
        elif scope == SkillScope.TEAM:
            await self._repo.save_team(skill)
        else:
            await self._repo.save_company(skill)
