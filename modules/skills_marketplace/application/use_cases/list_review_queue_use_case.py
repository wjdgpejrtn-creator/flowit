from __future__ import annotations

from common_schemas import UserRole
from common_schemas.exceptions import AuthorizationError

from ...domain.entities.marketplace_personal_skill import MarketplacePersonalSkill
from ...domain.ports.skill_repository import SkillRepository
from ...domain.value_objects.skill_state import SkillState


class ListReviewQueueUseCase:
    """관리자 리뷰 큐 — REVIEW 상태로 제출된 개인 스킬을 소유자 무관하게 나열 (REQ-013).

    스킬빌더에서 owner가 `SubmitSkillUseCase`로 DRAFT→REVIEW 제출한 스킬을, 관리자가 한 곳에서
    모아 보고 승인(`ApproveSkillUseCase`)/게시(`PublishSkillUseCase`)한다. api_server
    `GET /skills/review-queue` 라우트가 조립.

    인가(Admin only): `SkillApprovalPolicy`는 단건 승인/게시의 scope별 actor 인가를 다루지만,
    리뷰 큐는 전체 소유자의 스킬을 모아 보는 cross-user 조회이므로 **Admin superuser만** 허용한다
    (PermissionResolver Admin=전체 scope와 정합). 비-Admin은 fail-closed로 AuthorizationError.
    """

    def __init__(self, repo: SkillRepository) -> None:
        self._repo = repo

    async def execute(
        self,
        actor_role: UserRole,
        limit: int = 50,
        offset: int = 0,
    ) -> list[MarketplacePersonalSkill]:
        if actor_role != "Admin":
            raise AuthorizationError(
                "리뷰 큐 조회는 Admin만 가능합니다", code="E-PERM-001"
            )
        return await self._repo.list_personal_by_state(
            SkillState.REVIEW,
            limit=limit,
            offset=offset,
        )
