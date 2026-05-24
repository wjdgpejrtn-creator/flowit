from uuid import uuid4

from auth.domain.services.permission_resolver import PermissionResolver


def test_admin_gets_restricted_ceiling():
    resolver = PermissionResolver()
    perm = resolver.resolve(
        user_id=uuid4(),
        role="Admin",
        department_id=uuid4(),
        session_id=uuid4(),
    )
    assert perm.risk_ceiling == "Restricted"
    assert "Public" in perm.granted_scopes
    assert "Team" in perm.granted_scopes
    assert "Private" in perm.granted_scopes


def test_user_gets_high_ceiling():
    resolver = PermissionResolver()
    perm = resolver.resolve(
        user_id=uuid4(),
        role="User",
        department_id=uuid4(),
        session_id=uuid4(),
    )
    assert perm.risk_ceiling == "High"
    assert perm.granted_scopes == ["Private"]


def test_manager_roles_get_user_level_ceiling():
    """team_manager/company_manager는 워크플로우 scope/risk가 일반 User와 동일 —
    매니저 권한은 스킬 승인(SkillApprovalPolicy)에만 적용된다."""
    resolver = PermissionResolver()
    for role in ("team_manager", "company_manager"):
        perm = resolver.resolve(
            user_id=uuid4(),
            role=role,
            department_id=uuid4(),
            session_id=uuid4(),
        )
        assert perm.role == role
        assert perm.risk_ceiling == "High"
        assert perm.granted_scopes == ["Private"]


def test_permission_source_is_frozen():
    resolver = PermissionResolver()
    perm = resolver.resolve(uuid4(), "User", uuid4(), uuid4())
    try:
        perm.role = "Admin"  # type: ignore
        assert False, "Should be immutable"
    except Exception:
        pass
