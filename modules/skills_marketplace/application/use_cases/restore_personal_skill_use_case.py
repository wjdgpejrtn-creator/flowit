from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from common_schemas.exceptions import AuthorizationError, NotFoundError

from ...domain.ports.skill_repository import SkillRepository
from ...domain.services.skill_lifecycle import SkillLifecycle
from ...domain.value_objects.skill_state import SkillState


class RestorePersonalSkillUseCase:
    """개인 스킬 복원 — ARCHIVED → PUBLISHED (REQ-013, 마켓플레이스 보관/복원).

    보관(`ArchivePersonalSkillUseCase`)의 역연산 — 보관된 개인 스킬을 다시 게시 상태로 되돌려
    마켓플레이스/검색에 재노출한다. 신뢰 경계는 보관과 동일(owner만, fail-closed).

    상태 가드: `SkillLifecycle.transition`이 ARCHIVED 외 상태면 거부(E-SKILL-002). ARCHIVED→
    PUBLISHED 전이는 보관/복원 UX 계약에 맞춰 lifecycle에 명시돼 있다(skill_lifecycle.py).
    """

    def __init__(self, repo: SkillRepository) -> None:
        self._repo = repo

    async def execute(self, skill_id: UUID, actor_user_id: UUID) -> None:
        skill = await self._repo.get_personal(skill_id)
        if skill is None:
            raise NotFoundError(f"Personal skill {skill_id} not found")
        if skill.owner_user_id != actor_user_id:
            raise AuthorizationError(
                f"User {actor_user_id} is not the owner of personal skill {skill_id}"
            )

        new_state = SkillLifecycle.transition(
            SkillState(skill.lifecycle_state), SkillState.PUBLISHED
        )
        updated = skill.model_copy(
            update={"lifecycle_state": new_state, "updated_at": datetime.now(UTC)}
        )
        await self._repo.save_personal(updated)
