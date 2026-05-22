"""Skills Marketplace 게시 lifecycle 라우트 테스트 (ADR-0020 Q4).

라우트는 인증·요청 검증·use case 위임만 담당 — use case는 mock으로 대체하고
호출 인자/응답 매핑/도메인 예외→HTTP 변환을 검증한다.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import jwt as pyjwt
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.dependencies.permission import get_permission_source
from app.dependencies.use_cases import get_approve_skill_use_case, get_publish_skill_use_case
from app.main import create_app
from common_schemas import PermissionSource
from common_schemas.exceptions import NotFoundError

_REVIEWER_ID = uuid4()


@pytest.fixture
def app(env_minimum: None):
    return create_app(Settings())  # type: ignore[call-arg]


def _override_permission(app) -> None:
    """AuthMiddleware 우회 — reviewer_id 검증용 고정 user_id 주입."""
    fake_permission = PermissionSource(
        user_id=_REVIEWER_ID,
        role="Admin",  # type: ignore[arg-type]
        department_id=uuid4(),
        session_id=uuid4(),
        granted_scopes=["Private"],
        risk_ceiling="High",
    )
    app.dependency_overrides[get_permission_source] = lambda: fake_permission


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


def test_approve_skill_approved(app) -> None:
    use_case = MagicMock()
    use_case.execute = AsyncMock(return_value=None)
    app.dependency_overrides[get_approve_skill_use_case] = lambda: use_case
    _override_permission(app)

    skill_id = uuid4()
    client = TestClient(app)
    resp = client.post(
        f"/api/v1/skills/{skill_id}/approve",
        json={"scope": "team", "approved": True, "comment": "LGTM"},
        headers=_headers(),
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body == {"skill_id": str(skill_id), "scope": "team", "action": "approved"}
    use_case.execute.assert_awaited_once_with(
        skill_id=skill_id,
        scope="team",
        reviewer_id=_REVIEWER_ID,
        approved=True,
        comment="LGTM",
    )
    app.dependency_overrides.clear()


def test_approve_skill_rejected(app) -> None:
    use_case = MagicMock()
    use_case.execute = AsyncMock(return_value=None)
    app.dependency_overrides[get_approve_skill_use_case] = lambda: use_case
    _override_permission(app)

    skill_id = uuid4()
    client = TestClient(app)
    resp = client.post(
        f"/api/v1/skills/{skill_id}/approve",
        json={"scope": "personal", "approved": False},
        headers=_headers(),
    )

    assert resp.status_code == 200
    assert resp.json()["action"] == "rejected"
    use_case.execute.assert_awaited_once_with(
        skill_id=skill_id,
        scope="personal",
        reviewer_id=_REVIEWER_ID,
        approved=False,
        comment=None,
    )
    app.dependency_overrides.clear()


def test_publish_skill(app) -> None:
    use_case = MagicMock()
    use_case.execute = AsyncMock(return_value=None)
    app.dependency_overrides[get_publish_skill_use_case] = lambda: use_case
    _override_permission(app)

    skill_id = uuid4()
    client = TestClient(app)
    resp = client.post(
        f"/api/v1/skills/{skill_id}/publish",
        json={"scope": "company"},
        headers=_headers(),
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body == {"skill_id": str(skill_id), "scope": "company", "action": "published"}
    use_case.execute.assert_awaited_once_with(skill_id=skill_id, scope="company")
    app.dependency_overrides.clear()


def test_approve_skill_not_found_maps_404(app) -> None:
    """use case가 NotFoundError를 던지면 error_handler가 404로 매핑."""
    use_case = MagicMock()
    use_case.execute = AsyncMock(side_effect=NotFoundError("Skill not found"))
    app.dependency_overrides[get_approve_skill_use_case] = lambda: use_case
    _override_permission(app)

    client = TestClient(app)
    resp = client.post(
        f"/api/v1/skills/{uuid4()}/approve",
        json={"scope": "team", "approved": True},
        headers=_headers(),
    )

    assert resp.status_code == 404
    app.dependency_overrides.clear()


def test_approve_invalid_scope_maps_422(app) -> None:
    """SkillScope enum 밖의 값 → FastAPI 요청 검증 422."""
    use_case = MagicMock()
    use_case.execute = AsyncMock(return_value=None)
    app.dependency_overrides[get_approve_skill_use_case] = lambda: use_case
    _override_permission(app)

    client = TestClient(app)
    resp = client.post(
        f"/api/v1/skills/{uuid4()}/approve",
        json={"scope": "global", "approved": True},
        headers=_headers(),
    )

    assert resp.status_code == 422
    use_case.execute.assert_not_awaited()
    app.dependency_overrides.clear()


def test_skills_routes_require_bearer(app) -> None:
    """AuthMiddleware가 /skills/* 차단 검증 — Bearer 없으면 401."""
    client = TestClient(app)
    approve = client.post(
        f"/api/v1/skills/{uuid4()}/approve",
        json={"scope": "team", "approved": True},
    )
    publish = client.post(f"/api/v1/skills/{uuid4()}/publish", json={"scope": "team"})
    assert approve.status_code == 401
    assert publish.status_code == 401
