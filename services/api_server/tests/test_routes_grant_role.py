"""Admin role-grant 라우트 테스트 (스킬 마켓플레이스 RBAC, PR #150 위임2).

라우트는 인증·요청 검증·use case 위임만 담당 — use case는 mock으로 대체하고
호출 인자/응답 매핑/도메인 예외→HTTP 변환을 검증한다. 인가 게이트 자체는
GrantUserRoleUseCase 단위 테스트에서 검증한다.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import jwt as pyjwt
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.dependencies.auth import get_grant_user_role_use_case
from app.dependencies.permission import get_permission_source
from app.main import create_app
from auth.domain.entities.user import User
from common_schemas import PermissionSource
from common_schemas.exceptions import AuthorizationError, NotFoundError, ValidationError


@pytest.fixture
def app(env_minimum: None):
    return create_app(Settings())  # type: ignore[call-arg]


def _override_permission(app, role: str = "Admin") -> PermissionSource:
    actor = PermissionSource(
        user_id=uuid4(),
        role=role,  # type: ignore[arg-type]
        department_id=uuid4(),
        session_id=uuid4(),
        granted_scopes=["Private"],
        risk_ceiling="High",
    )
    app.dependency_overrides[get_permission_source] = lambda: actor
    return actor


def _bearer_token() -> str:
    now = datetime.now(UTC)
    return pyjwt.encode(
        {
            "sub": str(uuid4()),
            "session_hash": "dummy-hash",
            "type": "access",
            "exp": now + timedelta(seconds=3600),
            "iat": now,
        },
        "",
        algorithm="HS256",
    )


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {_bearer_token()}"}


def _user(user_id, role: str, department_id) -> User:
    now = datetime.now(UTC)
    return User(
        user_id=user_id,
        email="dev@example.com",
        name="Dev",
        role=role,  # type: ignore[arg-type]
        department_id=department_id,
        created_at=now,
        updated_at=now,
    )


def test_grant_role_team_manager(app) -> None:
    target_id = uuid4()
    dept = uuid4()
    use_case = MagicMock()
    use_case.execute = AsyncMock(return_value=_user(target_id, "team_manager", dept))
    app.dependency_overrides[get_grant_user_role_use_case] = lambda: use_case
    actor = _override_permission(app)

    client = TestClient(app)
    resp = client.put(
        f"/api/v1/auth/users/{target_id}/role",
        json={"role": "team_manager", "department_id": str(dept)},
        headers=_headers(),
    )

    assert resp.status_code == 200
    assert resp.json() == {
        "user_id": str(target_id),
        "role": "team_manager",
        "department_id": str(dept),
    }
    use_case.execute.assert_awaited_once_with(
        actor=actor,
        target_user_id=target_id,
        role="team_manager",
        department_id=dept,
    )
    app.dependency_overrides.clear()


def test_grant_role_forbidden_maps_403(app) -> None:
    """use case가 AuthorizationError(비-Admin actor)를 던지면 error_handler가 403으로 매핑."""
    use_case = MagicMock()
    use_case.execute = AsyncMock(side_effect=AuthorizationError("Only Admin can grant user roles"))
    app.dependency_overrides[get_grant_user_role_use_case] = lambda: use_case
    _override_permission(app, role="team_manager")

    client = TestClient(app)
    resp = client.put(
        f"/api/v1/auth/users/{uuid4()}/role",
        json={"role": "company_manager"},
        headers=_headers(),
    )

    assert resp.status_code == 403
    app.dependency_overrides.clear()


def test_grant_role_not_found_maps_404(app) -> None:
    use_case = MagicMock()
    use_case.execute = AsyncMock(side_effect=NotFoundError("User not found"))
    app.dependency_overrides[get_grant_user_role_use_case] = lambda: use_case
    _override_permission(app)

    client = TestClient(app)
    resp = client.put(
        f"/api/v1/auth/users/{uuid4()}/role",
        json={"role": "company_manager"},
        headers=_headers(),
    )

    assert resp.status_code == 404
    app.dependency_overrides.clear()


def test_grant_role_validation_maps_400(app) -> None:
    """team_manager + department_id 누락 → use case ValidationError → 400."""
    use_case = MagicMock()
    use_case.execute = AsyncMock(side_effect=ValidationError("team_manager requires a department_id"))
    app.dependency_overrides[get_grant_user_role_use_case] = lambda: use_case
    _override_permission(app)

    client = TestClient(app)
    resp = client.put(
        f"/api/v1/auth/users/{uuid4()}/role",
        json={"role": "team_manager"},
        headers=_headers(),
    )

    assert resp.status_code == 400
    app.dependency_overrides.clear()


def test_grant_role_invalid_role_maps_422(app) -> None:
    """UserRole Literal 밖의 값 → FastAPI 요청 검증 422."""
    use_case = MagicMock()
    use_case.execute = AsyncMock(return_value=None)
    app.dependency_overrides[get_grant_user_role_use_case] = lambda: use_case
    _override_permission(app)

    client = TestClient(app)
    resp = client.put(
        f"/api/v1/auth/users/{uuid4()}/role",
        json={"role": "superuser"},
        headers=_headers(),
    )

    assert resp.status_code == 422
    use_case.execute.assert_not_awaited()
    app.dependency_overrides.clear()


def test_grant_role_requires_bearer(app) -> None:
    """AuthMiddleware가 인증 없는 요청을 401로 차단."""
    client = TestClient(app)
    resp = client.put(
        f"/api/v1/auth/users/{uuid4()}/role",
        json={"role": "company_manager"},
    )
    assert resp.status_code == 401
