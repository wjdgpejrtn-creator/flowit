from __future__ import annotations

from uuid import UUID

from ...domain.entities.marketplace_personal_skill import MarketplacePersonalSkill
from ...domain.ports.skill_repository import SkillRepository
from ...domain.value_objects.skill_state import SkillState


class ListUserPersonalSkillsUseCase:
    """사용자 본인의 개인 스킬 목록 조회 — personal skills 미리보기 UI (REQ-013, 가원 요청).

    api_server `GET /skills/personal` 라우트가 조립. 호출부(api_server)가 `PermissionSource`에서
    추출한 현재 사용자 `user_id`를 그대로 넘긴다 — 타인 스킬 노출 방지(스코프는 user_id로 보장).
    `lifecycle_state`로 상태 필터(예: DRAFT만), `limit`/`offset`로 페이지네이션.
    """

    def __init__(self, repo: SkillRepository) -> None:
        self._repo = repo

    async def execute(
        self,
        user_id: UUID,
        lifecycle_state: SkillState | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[MarketplacePersonalSkill]:
        return await self._repo.list_personal_by_user(
            user_id,
            lifecycle_state=lifecycle_state,
            limit=limit,
            offset=offset,
        )
