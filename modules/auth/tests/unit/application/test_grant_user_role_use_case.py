from __future__ import annotations

from uuid import uuid4

import pytest
from auth.application.use_cases.grant_user_role_use_case import GrantUserRoleUseCase
from common_schemas import PermissionSource
from common_schemas.exceptions import AuthorizationError, NotFoundError, ValidationError


def _actor(role: str) -> PermissionSource:
    return PermissionSource(
        user_id=uuid4(),
        role=role,
        department_id=uuid4(),
        session_id=uuid4(),
        granted_scopes=["Private"],
        risk_ceiling="High",
    )


@pytest.mark.asyncio
async def test_admin_grants_team_manager(user_repo):
    target = await user_repo.create(uuid4(), "dev@example.com", "Dev")
    dept = uuid4()
    uc = GrantUserRoleUseCase(user_repo)

    result = await uc.execute(
        actor=_actor("Admin"),
        target_user_id=target.user_id,
        role="team_manager",
        department_id=dept,
    )

    assert result.role == "team_manager"
    assert result.department_id == dept
    stored = await user_repo.find_by_id(target.user_id)
    assert stored.role == "team_manager"
    assert stored.department_id == dept


@pytest.mark.asyncio
async def test_admin_grants_company_manager_without_department(user_repo):
    target = await user_repo.create(uuid4(), "exec@example.com", "Exec")
    uc = GrantUserRoleUseCase(user_repo)

    result = await uc.execute(
        actor=_actor("Admin"),
        target_user_id=target.user_id,
        role="company_manager",
    )

    assert result.role == "company_manager"
    assert result.department_id is None


@pytest.mark.asyncio
async def test_non_admin_actor_rejected(user_repo):
    target = await user_repo.create(uuid4(), "dev@example.com", "Dev")
    uc = GrantUserRoleUseCase(user_repo)

    for actor_role in ("User", "team_manager", "company_manager"):
        with pytest.raises(AuthorizationError):
            await uc.execute(
                actor=_actor(actor_role),
                target_user_id=target.user_id,
                role="team_manager",
                department_id=uuid4(),
            )


@pytest.mark.asyncio
async def test_team_manager_requires_department(user_repo):
    target = await user_repo.create(uuid4(), "dev@example.com", "Dev")
    uc = GrantUserRoleUseCase(user_repo)

    with pytest.raises(ValidationError):
        await uc.execute(
            actor=_actor("Admin"),
            target_user_id=target.user_id,
            role="team_manager",
            department_id=None,
        )


@pytest.mark.asyncio
async def test_target_user_not_found(user_repo):
    uc = GrantUserRoleUseCase(user_repo)

    with pytest.raises(NotFoundError):
        await uc.execute(
            actor=_actor("Admin"),
            target_user_id=uuid4(),
            role="company_manager",
        )
