from __future__ import annotations

from uuid import UUID

from common_schemas import UserRole
from common_schemas.exceptions import AuthorizationError

from ..value_objects.skill_scope import SkillScope


class SkillApprovalPolicy:
    """스킬 게시 lifecycle(승인/게시) actor 인가 규칙 (ADR-0020 위임2, 순수 도메인).

    scope별 인가 (role base — 조장 role 인프라 PR #157):
    - Admin    : superuser — 모든 scope 허용 (2026-05-24 결정, PermissionResolver Admin=전체 scope 정합)
    - personal : actor 본인이 소유자 (`actor_user_id == skill_owner_user_id`) — Ownership(E-PERM-002)
    - team     : actor가 `team_manager` AND 같은 부서 (`actor_department_id == skill_team_id`) — RBAC(E-PERM-001)
                 (department = 팀 레지스트리, `departments` seed — team_id↔department_id 값 정합은
                  FK 부재로 호출부가 보장)
    - company  : actor가 `company_manager` (단일 테넌트라 부서 매칭 불필요) — RBAC(E-PERM-001)

    role 값/타입 SSOT = `common_schemas.UserRole`(PR #157). use case가 actor 정보를 primitive로
    전달하며, 본 정책은 `PermissionSource`에 직접 의존하지 않는다(도메인 순수성 + 입력 최소화).
    인가 실패는 예외(fail-closed) — 알 수 없는 scope도 거부.
    """

    @staticmethod
    def authorize(
        *,
        scope: SkillScope,
        actor_user_id: UUID,
        actor_role: UserRole,
        actor_department_id: UUID | None,
        skill_owner_user_id: UUID | None,
        skill_team_id: UUID | None,
    ) -> None:
        """인가 성공 시 `None`, 실패 시 `AuthorizationError`."""
        # Admin은 superuser — 모든 scope 승인/게시 허용 (PermissionResolver의 Admin=전체 scope와 정합)
        if actor_role == "Admin":
            return
        if scope == SkillScope.PERSONAL:
            if skill_owner_user_id is None or actor_user_id != skill_owner_user_id:
                raise AuthorizationError(
                    "personal 스킬 승인/게시는 소유자 본인만 가능",
                    code="E-PERM-002",
                )
            return
        if scope == SkillScope.TEAM:
            if (
                actor_role != "team_manager"
                or actor_department_id is None
                or actor_department_id != skill_team_id
            ):
                raise AuthorizationError(
                    "team 스킬 승인/게시는 같은 부서 team_manager만 가능",
                    code="E-PERM-001",
                )
            return
        if scope == SkillScope.COMPANY:
            if actor_role != "company_manager":
                raise AuthorizationError(
                    "company 스킬 승인/게시는 company_manager만 가능",
                    code="E-PERM-001",
                )
            return
        # fail-closed: 정의되지 않은 scope는 거부
        raise AuthorizationError(f"알 수 없는 scope: {scope!r}", code="E-PERM-001")
