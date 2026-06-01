from __future__ import annotations

from common_schemas import UserRole
from common_schemas.exceptions import AuthorizationError

from ...domain.entities.marketplace_company_skill import MarketplaceCompanySkill
from ...domain.entities.marketplace_personal_skill import MarketplacePersonalSkill
from ...domain.entities.marketplace_team_skill import MarketplaceTeamSkill
from ...domain.ports.skill_repository import SkillRepository
from ...domain.value_objects.skill_scope import SkillScope
from ...domain.value_objects.skill_state import SkillState


class ListReviewQueueUseCase:
    """관리자 리뷰 큐 — REVIEW 상태로 올라온 스킬을 scope별로 모아 나열 (REQ-013).

    - ``personal``: owner가 `SubmitSkillUseCase`로 DRAFT→REVIEW 제출한 개인 스킬(소유자 무관)
      — `list_personal_by_state(REVIEW)`.
    - ``team`` / ``company``: 하위 scope에서 **승격 요청**(promote→submit)되어 REVIEW로 올라온
      스킬 — `list_by_scope(scope, REVIEW)`. 승격은 상위 scope에 새 스킬을 DRAFT로 복제한 뒤
      submit으로 REVIEW 전이하므로(api_server `POST /{id}/promote`), 이 큐에 나타난다.

    관리자가 한 곳에서 모아 보고 승인(`ApproveSkillUseCase`)/게시(`PublishSkillUseCase`)한다.

    인가(Admin only): 단건 승인/게시의 scope별 actor 인가는 `SkillApprovalPolicy`가 다루지만,
    리뷰 큐는 전체 소유자/팀의 스킬을 모아 보는 cross-user 조회이므로 **Admin superuser만** 허용한다
    (PermissionResolver Admin=전체 scope와 정합). 비-Admin은 fail-closed로 AuthorizationError.
    """

    def __init__(self, repo: SkillRepository) -> None:
        self._repo = repo

    async def execute(
        self,
        actor_role: UserRole,
        scope: SkillScope = SkillScope.PERSONAL,
        limit: int = 50,
        offset: int = 0,
    ) -> list[MarketplacePersonalSkill | MarketplaceTeamSkill | MarketplaceCompanySkill]:
        if actor_role != "Admin":
            raise AuthorizationError(
                "리뷰 큐 조회는 Admin만 가능합니다", code="E-PERM-001"
            )
        if scope == SkillScope.PERSONAL:
            return await self._repo.list_personal_by_state(
                SkillState.REVIEW,
                limit=limit,
                offset=offset,
            )
        # team/company — 승격 요청으로 REVIEW에 올라온 상위 scope 스킬.
        return await self._repo.list_by_scope(
            scope,
            lifecycle_state=SkillState.REVIEW,
            limit=limit,
            offset=offset,
        )
