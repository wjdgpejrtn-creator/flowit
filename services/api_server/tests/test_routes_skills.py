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
from app.config import Settings
from app.dependencies.permission import get_permission_source
from app.dependencies.use_cases import (
    get_approve_skill_use_case,
    get_delete_personal_skill_use_case,
    get_get_personal_skill_use_case,
    get_list_personal_skills_use_case,
    get_publish_skill_use_case,
    get_update_personal_skill_use_case,
)
from app.main import create_app
from common_schemas import PermissionSource
from common_schemas.exceptions import AuthorizationError, NotFoundError, ValidationError
from fastapi.testclient import TestClient
from skills_marketplace.domain.entities.marketplace_personal_skill import MarketplacePersonalSkill
from skills_marketplace.domain.value_objects.skill_state import SkillState

_REVIEWER_ID = uuid4()


@pytest.fixture
def app(env_minimum: None):
    return create_app(Settings())  # type: ignore[call-arg]


def _override_permission(app) -> PermissionSource:
    """AuthMiddleware 우회 — actor(user_id/role/department_id) 주입.

    role="User"로 설정 — 라우트 단위 테스트는 use case를 mock하므로 actor 인자
    pass-through만 검증한다(실제 인가 판정은 `SkillApprovalPolicy` 단위 테스트 영역).
    반환된 PermissionSource로 호출자가 `actor_department_id` 등 검증에 활용 가능.
    """
    fake_permission = PermissionSource(
        user_id=_REVIEWER_ID,
        role="User",  # type: ignore[arg-type]
        department_id=uuid4(),
        session_id=uuid4(),
        granted_scopes=["Private"],
        risk_ceiling="High",
    )
    app.dependency_overrides[get_permission_source] = lambda: fake_permission
    return fake_permission


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
    perm = _override_permission(app)

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
        actor_role="User",
        actor_department_id=perm.department_id,
    )
    app.dependency_overrides.clear()


def test_approve_skill_rejected(app) -> None:
    use_case = MagicMock()
    use_case.execute = AsyncMock(return_value=None)
    app.dependency_overrides[get_approve_skill_use_case] = lambda: use_case
    perm = _override_permission(app)

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
        actor_role="User",
        actor_department_id=perm.department_id,
    )
    app.dependency_overrides.clear()


def test_publish_skill(app) -> None:
    use_case = MagicMock()
    use_case.execute = AsyncMock(return_value=None)
    app.dependency_overrides[get_publish_skill_use_case] = lambda: use_case
    perm = _override_permission(app)

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
    use_case.execute.assert_awaited_once_with(
        skill_id=skill_id,
        scope="company",
        actor_user_id=_REVIEWER_ID,
        actor_role="User",
        actor_department_id=perm.department_id,
    )
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


# ── Personal CRUD (REQ-013) ──────────────────────────────────────────────────


def _personal_skill(
    skill_id, owner_id, *, name="블로그 요약", state: SkillState = SkillState.DRAFT
) -> MarketplacePersonalSkill:
    now = datetime.now(UTC)
    return MarketplacePersonalSkill(
        skill_id=skill_id,
        owner_user_id=owner_id,
        name=name,
        description="설명",
        lifecycle_state=state,
        skill_document_uri="gs://bucket/skills/x/SKILL.md",
        tags=["productivity"],
        created_at=now,
        updated_at=now,
    )


def test_list_personal_skills_passes_user_and_filters(app) -> None:
    sid = uuid4()
    skill = _personal_skill(sid, _REVIEWER_ID)
    use_case = MagicMock()
    use_case.execute = AsyncMock(return_value=[skill])
    app.dependency_overrides[get_list_personal_skills_use_case] = lambda: use_case
    _override_permission(app)

    client = TestClient(app)
    resp = client.get(
        "/api/v1/skills/personal",
        params={"lifecycle_state": "draft", "limit": 20, "offset": 5},
        headers=_headers(),
    )

    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["skill_id"] == str(sid)
    assert body[0]["lifecycle_state"] == "draft"
    # embedding/metadata/node_spec_staging는 응답에 노출 금지.
    assert "embedding" not in body[0]
    assert "metadata" not in body[0]
    assert "node_spec_staging" not in body[0]
    use_case.execute.assert_awaited_once_with(
        user_id=_REVIEWER_ID,
        lifecycle_state=SkillState.DRAFT,
        limit=20,
        offset=5,
    )
    app.dependency_overrides.clear()


def test_list_personal_skills_defaults_no_lifecycle(app) -> None:
    use_case = MagicMock()
    use_case.execute = AsyncMock(return_value=[])
    app.dependency_overrides[get_list_personal_skills_use_case] = lambda: use_case
    _override_permission(app)

    client = TestClient(app)
    resp = client.get("/api/v1/skills/personal", headers=_headers())

    assert resp.status_code == 200
    assert resp.json() == []
    use_case.execute.assert_awaited_once_with(
        user_id=_REVIEWER_ID, lifecycle_state=None, limit=50, offset=0
    )
    app.dependency_overrides.clear()


def test_list_personal_skills_invalid_lifecycle_maps_422(app) -> None:
    use_case = MagicMock()
    use_case.execute = AsyncMock(return_value=[])
    app.dependency_overrides[get_list_personal_skills_use_case] = lambda: use_case
    _override_permission(app)

    client = TestClient(app)
    resp = client.get(
        "/api/v1/skills/personal", params={"lifecycle_state": "not_a_state"}, headers=_headers()
    )
    assert resp.status_code == 422
    use_case.execute.assert_not_awaited()
    app.dependency_overrides.clear()


def test_get_personal_skill_owner_pass_through(app) -> None:
    sid = uuid4()
    skill = _personal_skill(sid, _REVIEWER_ID)
    use_case = MagicMock()
    use_case.execute = AsyncMock(return_value=skill)
    app.dependency_overrides[get_get_personal_skill_use_case] = lambda: use_case
    _override_permission(app)

    client = TestClient(app)
    resp = client.get(f"/api/v1/skills/personal/{sid}", headers=_headers())

    assert resp.status_code == 200
    assert resp.json()["skill_id"] == str(sid)
    use_case.execute.assert_awaited_once_with(skill_id=sid, actor_user_id=_REVIEWER_ID)
    app.dependency_overrides.clear()


def test_get_personal_skill_non_owner_maps_403(app) -> None:
    use_case = MagicMock()
    use_case.execute = AsyncMock(side_effect=AuthorizationError("not owner"))
    app.dependency_overrides[get_get_personal_skill_use_case] = lambda: use_case
    _override_permission(app)

    client = TestClient(app)
    resp = client.get(f"/api/v1/skills/personal/{uuid4()}", headers=_headers())
    assert resp.status_code == 403
    app.dependency_overrides.clear()


def test_get_personal_skill_not_found_maps_404(app) -> None:
    use_case = MagicMock()
    use_case.execute = AsyncMock(side_effect=NotFoundError("not found"))
    app.dependency_overrides[get_get_personal_skill_use_case] = lambda: use_case
    _override_permission(app)

    client = TestClient(app)
    resp = client.get(f"/api/v1/skills/personal/{uuid4()}", headers=_headers())
    assert resp.status_code == 404
    app.dependency_overrides.clear()


def test_update_personal_skill_partial_body(app) -> None:
    sid = uuid4()
    updated = _personal_skill(sid, _REVIEWER_ID, name="새 이름")
    use_case = MagicMock()
    use_case.execute = AsyncMock(return_value=updated)
    app.dependency_overrides[get_update_personal_skill_use_case] = lambda: use_case
    _override_permission(app)

    client = TestClient(app)
    resp = client.put(
        f"/api/v1/skills/personal/{sid}",
        json={"name": "새 이름", "tags": ["a", "b"]},
        headers=_headers(),
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "새 이름"
    use_case.execute.assert_awaited_once_with(
        skill_id=sid,
        actor_user_id=_REVIEWER_ID,
        name="새 이름",
        description=None,
        tags=["a", "b"],
    )
    app.dependency_overrides.clear()


def test_update_personal_skill_lifecycle_validation_maps_400(app) -> None:
    """non-DRAFT 수정 시도 → use case가 ValidationError → 400."""
    use_case = MagicMock()
    use_case.execute = AsyncMock(side_effect=ValidationError("not draft"))
    app.dependency_overrides[get_update_personal_skill_use_case] = lambda: use_case
    _override_permission(app)

    client = TestClient(app)
    resp = client.put(
        f"/api/v1/skills/personal/{uuid4()}", json={"name": "x"}, headers=_headers()
    )
    assert resp.status_code == 400
    app.dependency_overrides.clear()


def test_delete_personal_skill_returns_204(app) -> None:
    use_case = MagicMock()
    use_case.execute = AsyncMock(return_value=None)
    app.dependency_overrides[get_delete_personal_skill_use_case] = lambda: use_case
    _override_permission(app)

    sid = uuid4()
    client = TestClient(app)
    resp = client.delete(f"/api/v1/skills/personal/{sid}", headers=_headers())

    assert resp.status_code == 204
    assert resp.content == b""
    use_case.execute.assert_awaited_once_with(skill_id=sid, actor_user_id=_REVIEWER_ID)
    app.dependency_overrides.clear()


def test_delete_personal_skill_non_owner_maps_403(app) -> None:
    use_case = MagicMock()
    use_case.execute = AsyncMock(side_effect=AuthorizationError("not owner"))
    app.dependency_overrides[get_delete_personal_skill_use_case] = lambda: use_case
    _override_permission(app)

    client = TestClient(app)
    resp = client.delete(f"/api/v1/skills/personal/{uuid4()}", headers=_headers())
    assert resp.status_code == 403
    app.dependency_overrides.clear()


def test_personal_routes_require_bearer(app) -> None:
    """AuthMiddleware가 /skills/personal* 차단 검증."""
    client = TestClient(app)
    sid = uuid4()
    assert client.get("/api/v1/skills/personal").status_code == 401
    assert client.get(f"/api/v1/skills/personal/{sid}").status_code == 401
    assert client.put(f"/api/v1/skills/personal/{sid}", json={}).status_code == 401
    assert client.delete(f"/api/v1/skills/personal/{sid}").status_code == 401
