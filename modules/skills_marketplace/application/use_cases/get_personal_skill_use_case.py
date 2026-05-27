from __future__ import annotations

from uuid import UUID

from common_schemas.exceptions import AuthorizationError, NotFoundError

from ...domain.entities.marketplace_personal_skill import MarketplacePersonalSkill
from ...domain.ports.skill_repository import SkillRepository


class GetPersonalSkillUseCase:
    """개인 스킬 단건 조회 — personal skills 미리보기 UI (REQ-013, 가원 요청).

    api_server `GET /skills/personal/{id}` 라우트가 조립. 신뢰 경계는 Update/Delete와 동일:

    - 인가: **owner만**(`actor_user_id == owner_user_id`) — 아니면 `AuthorizationError`(fail-closed).
      `SkillApprovalPolicy`의 personal 규칙(actor==owner)과 일관. 다른 사용자의 스킬 노출 차단.

    Update/Delete가 동일 패턴(`get_personal` → owner 검사)을 반복하므로 별도 use case로 분리해
    라우터가 보안 로직을 직접 들고 있지 않도록 한다.
    """

    def __init__(self, repo: SkillRepository) -> None:
        self._repo = repo

    async def execute(self, skill_id: UUID, actor_user_id: UUID) -> MarketplacePersonalSkill:
        skill = await self._repo.get_personal(skill_id)
        if skill is None:
            raise NotFoundError(f"Personal skill {skill_id} not found")

        if skill.owner_user_id != actor_user_id:
            raise AuthorizationError(
                f"User {actor_user_id} is not the owner of personal skill {skill_id}"
            )

        return skill
