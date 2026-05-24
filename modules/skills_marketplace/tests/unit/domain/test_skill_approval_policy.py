from __future__ import annotations

from uuid import uuid4

import pytest
from common_schemas.exceptions import AuthorizationError

from skills_marketplace.domain.services.skill_approval_policy import SkillApprovalPolicy
from skills_marketplace.domain.value_objects.skill_scope import SkillScope


class TestPersonalScope:
    """personal: actor 본인이 소유자여야 승인/게시 가능 (Ownership)."""

    def test_owner_authorized(self) -> None:
        uid = uuid4()
        SkillApprovalPolicy.authorize(
            scope=SkillScope.PERSONAL,
            actor_user_id=uid,
            actor_role="User",
            actor_department_id=None,
            skill_owner_user_id=uid,
            skill_team_id=None,
        )  # 예외 없음 = 인가

    def test_non_owner_denied(self) -> None:
        with pytest.raises(AuthorizationError):
            SkillApprovalPolicy.authorize(
                scope=SkillScope.PERSONAL,
                actor_user_id=uuid4(),
                actor_role="User",
                actor_department_id=None,
                skill_owner_user_id=uuid4(),
                skill_team_id=None,
            )


class TestTeamScope:
    """team: team_manager + 같은 부서(department_id == skill.team_id)."""

    def test_team_manager_same_dept_authorized(self) -> None:
        dept = uuid4()
        SkillApprovalPolicy.authorize(
            scope=SkillScope.TEAM,
            actor_user_id=uuid4(),
            actor_role="team_manager",
            actor_department_id=dept,
            skill_owner_user_id=None,
            skill_team_id=dept,
        )

    def test_non_manager_role_denied(self) -> None:
        dept = uuid4()
        with pytest.raises(AuthorizationError):
            SkillApprovalPolicy.authorize(
                scope=SkillScope.TEAM,
                actor_user_id=uuid4(),
                actor_role="User",
                actor_department_id=dept,
                skill_owner_user_id=None,
                skill_team_id=dept,
            )

    def test_team_manager_other_dept_denied(self) -> None:
        with pytest.raises(AuthorizationError):
            SkillApprovalPolicy.authorize(
                scope=SkillScope.TEAM,
                actor_user_id=uuid4(),
                actor_role="team_manager",
                actor_department_id=uuid4(),
                skill_owner_user_id=None,
                skill_team_id=uuid4(),
            )

    def test_team_manager_no_dept_denied(self) -> None:
        with pytest.raises(AuthorizationError):
            SkillApprovalPolicy.authorize(
                scope=SkillScope.TEAM,
                actor_user_id=uuid4(),
                actor_role="team_manager",
                actor_department_id=None,
                skill_owner_user_id=None,
                skill_team_id=uuid4(),
            )


class TestCompanyScope:
    """company: company_manager (단일 테넌트라 부서 매칭 불필요)."""

    def test_company_manager_authorized(self) -> None:
        SkillApprovalPolicy.authorize(
            scope=SkillScope.COMPANY,
            actor_user_id=uuid4(),
            actor_role="company_manager",
            actor_department_id=None,
            skill_owner_user_id=None,
            skill_team_id=None,
        )

    def test_team_manager_cannot_approve_company(self) -> None:
        with pytest.raises(AuthorizationError):
            SkillApprovalPolicy.authorize(
                scope=SkillScope.COMPANY,
                actor_user_id=uuid4(),
                actor_role="team_manager",
                actor_department_id=uuid4(),
                skill_owner_user_id=None,
                skill_team_id=None,
            )

    def test_plain_user_cannot_approve_company(self) -> None:
        with pytest.raises(AuthorizationError):
            SkillApprovalPolicy.authorize(
                scope=SkillScope.COMPANY,
                actor_user_id=uuid4(),
                actor_role="User",
                actor_department_id=None,
                skill_owner_user_id=None,
                skill_team_id=None,
            )


class TestAdminSuperuser:
    """Admin은 superuser — 모든 scope 승인/게시 가능 (2026-05-24 박아름 결정)."""

    def test_admin_approves_others_personal(self) -> None:
        SkillApprovalPolicy.authorize(
            scope=SkillScope.PERSONAL,
            actor_user_id=uuid4(),
            actor_role="Admin",
            actor_department_id=None,
            skill_owner_user_id=uuid4(),  # 타인 소유여도 허용
            skill_team_id=None,
        )

    def test_admin_approves_team_without_dept_match(self) -> None:
        SkillApprovalPolicy.authorize(
            scope=SkillScope.TEAM,
            actor_user_id=uuid4(),
            actor_role="Admin",
            actor_department_id=None,  # 부서 매칭 없어도 허용
            skill_owner_user_id=None,
            skill_team_id=uuid4(),
        )

    def test_admin_approves_company(self) -> None:
        SkillApprovalPolicy.authorize(
            scope=SkillScope.COMPANY,
            actor_user_id=uuid4(),
            actor_role="Admin",
            actor_department_id=None,
            skill_owner_user_id=None,
            skill_team_id=None,
        )
