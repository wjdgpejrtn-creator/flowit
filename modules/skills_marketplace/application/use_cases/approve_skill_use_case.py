from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from common_schemas.exceptions import NotFoundError

from ...domain.entities.approval_workflow import ApprovalWorkflow
from ...domain.ports.skill_repository import SkillRepository
from ...domain.services.skill_lifecycle import SkillLifecycle
from ...domain.value_objects.skill_scope import SkillScope
from ...domain.value_objects.skill_state import SkillState


class ApproveSkillUseCase:
    """스킬 게시 승인 — REVIEW → APPROVED (또는 반려 시 DRAFT).

    storage/marketplace/application/use_cases/approve_skill.py에서 이전 (ADR-0012 PR-2d).
    정석 정정: 원본은 `PgSkillRepository`(구현체) 직접 의존(anti-pattern)이었으나,
    `SkillRepository`(ABC) 의존으로 교체. scope별 get/save 분기.
    """

    def __init__(self, repo: SkillRepository) -> None:
        self._repo = repo

    async def execute(
        self,
        skill_id: UUID,
        scope: SkillScope,
        reviewer_id: UUID,
        approved: bool,
        comment: str | None = None,
    ) -> None:
        skill = await self._get(skill_id, scope)
        if skill is None:
            raise NotFoundError(f"Skill {skill_id} (scope={scope.value}) not found")

        target = SkillState.APPROVED if approved else SkillState.DRAFT
        new_state = SkillLifecycle.transition(SkillState(skill.lifecycle_state), target)
        now = datetime.now(UTC)
        updated = skill.model_copy(update={"lifecycle_state": new_state, "updated_at": now})
        await self._save(updated, scope)

        # ADR-0020 (+): 승인 결정을 ApprovalWorkflow 레코드로 저장 (감사 추적)
        await self._repo.save_approval(
            ApprovalWorkflow(
                approval_id=uuid4(),
                skill_id=skill_id,
                reviewer_id=reviewer_id,
                status="approved" if approved else "rejected",
                comment=comment,
                reviewed_at=now,
                created_at=now,
            )
        )

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
