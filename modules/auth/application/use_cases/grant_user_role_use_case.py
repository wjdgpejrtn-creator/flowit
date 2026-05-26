from __future__ import annotations

from uuid import UUID

from common_schemas import PermissionSource
from common_schemas.exceptions import AuthorizationError, NotFoundError, ValidationError

from ...domain.entities.user import User, UserRole
from ...domain.ports.user_repository import UserRepository


class GrantUserRoleUseCase:
    """Admin이 다른 사용자의 역할(role)과 소속 팀(department_id)을 변경한다.

    스킬 마켓플레이스 RBAC: team scope 승인은 `actor.department_id == skill.team_id`
    매칭에 의존하므로, `team_manager` 부여 시 department_id를 반드시 함께 지정한다.
    """

    def __init__(self, user_repo: UserRepository) -> None:
        self._user_repo = user_repo

    async def execute(
        self,
        *,
        actor: PermissionSource,
        target_user_id: UUID,
        role: UserRole,
        department_id: UUID | None = None,
    ) -> User:
        if actor.role != "Admin":
            raise AuthorizationError("Only Admin can grant user roles", code="E-PERM-001")

        if role == "team_manager" and department_id is None:
            raise ValidationError("team_manager requires a department_id")

        target = await self._user_repo.find_by_id(target_user_id)
        if target is None:
            raise NotFoundError(f"User {target_user_id} not found")

        await self._user_repo.update_role(target_user_id, role)
        await self._user_repo.update_department(target_user_id, department_id)

        return target.model_copy(update={"role": role, "department_id": department_id})
