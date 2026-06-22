from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from common_schemas.exceptions import AuthorizationError, NotFoundError

from ...domain.ports.skill_repository import SkillRepository
from ...domain.services.skill_lifecycle import SkillLifecycle
from ...domain.value_objects.skill_state import SkillState


class ArchivePersonalSkillUseCase:
    """개인 스킬 보관 — PUBLISHED → ARCHIVED (REQ-013, 마켓플레이스 보관/복원).

    보관은 게시된 개인 스킬을 마켓플레이스/검색 노출에서 임시로 내리는 가역 동작이다(복원은
    `RestorePersonalSkillUseCase`). 신뢰 경계는 Get/Update/Delete personal과 동일:

    - 인가: **owner만**(`actor_user_id == owner_user_id`) — 아니면 `AuthorizationError`(fail-closed).
      `SkillApprovalPolicy`의 personal 규칙(actor==owner)과 일관.
    - 상태 가드: `SkillLifecycle.transition`이 PUBLISHED 외 상태면 거부(E-SKILL-002).
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
            SkillState(skill.lifecycle_state), SkillState.ARCHIVED
        )
        updated = skill.model_copy(
            update={"lifecycle_state": new_state, "updated_at": datetime.now(UTC)}
        )
        await self._repo.save_personal(updated)
