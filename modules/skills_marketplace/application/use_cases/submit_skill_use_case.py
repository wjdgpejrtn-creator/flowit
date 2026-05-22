from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from common_schemas.exceptions import NotFoundError

from ...domain.ports.skill_repository import SkillRepository
from ...domain.services.skill_lifecycle import SkillLifecycle
from ...domain.value_objects.skill_scope import SkillScope
from ...domain.value_objects.skill_state import SkillState


class SubmitSkillUseCase:
    """스킬 게시 검토 제출 — DRAFT → REVIEW (ADR-0020 Q4, PR #150 조장 위임).

    Skills Builder가 생성한 personal DRAFT 스킬을 검토(REVIEW) 단계로 제출한다.
    api_server submit 라우트(REQ-009)가 이 use case를 조립 — 라우트가 도메인 전이를
    직접 수행하면 Composition Root 원칙 위반이라 use case가 선행돼야 한다.
    `ApproveSkillUseCase`(REVIEW→APPROVED) / `PublishSkillUseCase`(APPROVED→PUBLISHED)와 동일 패턴.
    """

    def __init__(self, repo: SkillRepository) -> None:
        self._repo = repo

    async def execute(self, skill_id: UUID, scope: SkillScope) -> None:
        skill = await self._get(skill_id, scope)
        if skill is None:
            raise NotFoundError(f"Skill {skill_id} (scope={scope.value}) not found")

        new_state = SkillLifecycle.transition(SkillState(skill.lifecycle_state), SkillState.REVIEW)
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
