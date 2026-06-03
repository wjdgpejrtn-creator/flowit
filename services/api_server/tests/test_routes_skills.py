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
from app.dependencies.repositories import get_document_repository
from app.dependencies.use_cases import (
    get_approve_skill_use_case,
    get_create_draft_skill_use_case,
    get_delete_personal_skill_use_case,
    get_get_personal_skill_document_use_case,
    get_get_personal_skill_use_case,
    get_list_personal_skills_use_case,
    get_publish_skill_use_case,
    get_update_personal_skill_use_case,
)
from app.main import create_app
from common_schemas import PermissionSource, SkillDocument
from common_schemas.enums import RiskLevel
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
        instructions=None,
    )
    app.dependency_overrides.clear()


def test_update_personal_skill_passes_instructions(app) -> None:
    """instructions(SKILL.md 본문)가 body에 오면 use case로 전달 — GCS 재저장 트리거(ADR-0017)."""
    sid = uuid4()
    updated = _personal_skill(sid, _REVIEWER_ID, name="문서스킬")
    use_case = MagicMock()
    use_case.execute = AsyncMock(return_value=updated)
    app.dependency_overrides[get_update_personal_skill_use_case] = lambda: use_case
    _override_permission(app)

    client = TestClient(app)
    resp = client.put(
        f"/api/v1/skills/personal/{sid}",
        json={"description": "새 설명", "instructions": "# 새 지침서\n본문"},
        headers=_headers(),
    )

    assert resp.status_code == 200
    use_case.execute.assert_awaited_once_with(
        skill_id=sid,
        actor_user_id=_REVIEWER_ID,
        name=None,
        description="새 설명",
        tags=None,
        instructions="# 새 지침서\n본문",
    )
    app.dependency_overrides.clear()


def test_update_personal_skill_validation_maps_400(app) -> None:
    """use case ValidationError(예: 빈 name) → 400. (게시 스킬 수정은 더 이상 거부 대상 아님)"""
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
    assert client.get(f"/api/v1/skills/personal/{sid}/document").status_code == 401
    assert client.put(f"/api/v1/skills/personal/{sid}", json={}).status_code == 401
    assert client.delete(f"/api/v1/skills/personal/{sid}").status_code == 401


# ── Personal document (지침서 본문 lazy-load) ─────────────────────────────────


def test_get_personal_skill_document_returns_instructions(app) -> None:
    """GET /personal/{id}/document → owner 게이트 통과 시 SKILL.md 본문(instructions) 반환."""
    sid = uuid4()
    document = SkillDocument(
        skill_id=sid, name="문서스킬", description="설명", instructions="# 지침서\n본문"
    )
    use_case = MagicMock()
    use_case.execute = AsyncMock(return_value=document)
    app.dependency_overrides[get_get_personal_skill_document_use_case] = lambda: use_case
    _override_permission(app)

    client = TestClient(app)
    resp = client.get(f"/api/v1/skills/personal/{sid}/document", headers=_headers())

    assert resp.status_code == 200
    body = resp.json()
    assert body["instructions"] == "# 지침서\n본문"
    assert body["skill_id"] == str(sid)
    use_case.execute.assert_awaited_once_with(skill_id=sid, actor_user_id=_REVIEWER_ID)
    app.dependency_overrides.clear()


def test_get_personal_skill_document_missing_maps_404(app) -> None:
    """GCS에 지침서 없음(use case NotFoundError) → 404 → 프론트 graceful '지침서 없음'."""
    use_case = MagicMock()
    use_case.execute = AsyncMock(side_effect=NotFoundError("no document"))
    app.dependency_overrides[get_get_personal_skill_document_use_case] = lambda: use_case
    _override_permission(app)

    client = TestClient(app)
    resp = client.get(f"/api/v1/skills/personal/{uuid4()}/document", headers=_headers())
    assert resp.status_code == 404
    app.dependency_overrides.clear()


def test_get_personal_skill_document_non_owner_maps_403(app) -> None:
    use_case = MagicMock()
    use_case.execute = AsyncMock(side_effect=AuthorizationError("not owner"))
    app.dependency_overrides[get_get_personal_skill_document_use_case] = lambda: use_case
    _override_permission(app)

    client = TestClient(app)
    resp = client.get(f"/api/v1/skills/personal/{uuid4()}/document", headers=_headers())
    assert resp.status_code == 403
    app.dependency_overrides.clear()


# ── Personal create (REQ-010, 스킬빌더 폼 입구) ───────────────────────────────


def _override_create_trio(app, *, sid, created, update_uc=None, doc=...):
    """create/update/get 3개 use case + document repo 를 override 하고 mock 을 돌려준다.

    `doc_repo.get_by_id`는 기본적으로 _REVIEWER_ID 소유 문서를 반환(source_document_id
    검증 통과 경로). `doc=None`이면 미존재(404), 다른 user_id 문서를 주면 403 경로.
    """
    create_uc = MagicMock()
    create_uc.execute = AsyncMock(return_value=sid)
    get_uc = MagicMock()
    get_uc.execute = AsyncMock(return_value=created)
    update_uc = update_uc or MagicMock()
    if not isinstance(update_uc.execute, AsyncMock):
        update_uc.execute = AsyncMock(return_value=created)
    doc_repo = MagicMock()
    default_doc = MagicMock(user_id=_REVIEWER_ID) if doc is ... else doc
    doc_repo.get_by_id = AsyncMock(return_value=default_doc)
    app.dependency_overrides[get_create_draft_skill_use_case] = lambda: create_uc
    app.dependency_overrides[get_get_personal_skill_use_case] = lambda: get_uc
    app.dependency_overrides[get_update_personal_skill_use_case] = lambda: update_uc
    app.dependency_overrides[get_document_repository] = lambda: doc_repo
    return create_uc, update_uc, get_uc


def test_create_personal_skill_minimal(app) -> None:
    sid = uuid4()
    created = _personal_skill(sid, _REVIEWER_ID, name="새 스킬")
    create_uc, update_uc, get_uc = _override_create_trio(app, sid=sid, created=created)
    _override_permission(app)

    client = TestClient(app)
    resp = client.post(
        "/api/v1/skills/personal",
        json={"name": "새 스킬", "description": "설명"},
        headers=_headers(),
    )

    assert resp.status_code == 201
    body = resp.json()
    assert body["skill_id"] == str(sid)
    assert body["lifecycle_state"] == "draft"
    # tags 없으면 update 미호출 (불필요 write 방지).
    update_uc.execute.assert_not_awaited()
    get_uc.execute.assert_awaited_once_with(skill_id=sid, actor_user_id=_REVIEWER_ID)
    # create는 owner/name/description + placeholder node_spec_staging 로 위임.
    kwargs = create_uc.execute.await_args.kwargs
    assert kwargs["owner_user_id"] == _REVIEWER_ID
    assert kwargs["name"] == "새 스킬"
    assert kwargs["description"] == "설명"
    assert kwargs["instructions"] is None
    assert kwargs["source_document_id"] is None  # 직접 진입 — association 없음
    assert kwargs["node_spec_staging"].category == "action"
    assert kwargs["node_spec_staging"].risk_level == RiskLevel.LOW
    app.dependency_overrides.clear()


def test_create_personal_skill_persists_source_document_id(app) -> None:
    # REQ-010 문서→빌더 핸드오프: source_document_id 를 use case 로 전달
    sid = uuid4()
    doc_id = uuid4()
    created = _personal_skill(sid, _REVIEWER_ID, name="문서 기반")
    create_uc, _, _ = _override_create_trio(app, sid=sid, created=created)
    _override_permission(app)

    client = TestClient(app)
    resp = client.post(
        "/api/v1/skills/personal",
        json={"name": "문서 기반", "description": "설명", "source_document_id": str(doc_id)},
        headers=_headers(),
    )

    assert resp.status_code == 201
    assert create_uc.execute.await_args.kwargs["source_document_id"] == doc_id
    app.dependency_overrides.clear()


def test_create_personal_skill_unknown_source_document_404(app) -> None:
    # 없는 문서 id → FK 위반 500 이 아니라 404 (라우터 선검증)
    sid = uuid4()
    create_uc, _, _ = _override_create_trio(app, sid=sid, created=None, doc=None)
    _override_permission(app)

    client = TestClient(app)
    resp = client.post(
        "/api/v1/skills/personal",
        json={"name": "x", "description": "y", "source_document_id": str(uuid4())},
        headers=_headers(),
    )
    assert resp.status_code == 404
    create_uc.execute.assert_not_awaited()  # 검증 실패 시 생성 안 함
    app.dependency_overrides.clear()


def test_create_personal_skill_other_users_source_document_403(app) -> None:
    # 타 사용자 문서 id → FK 는 통과하지만 소유 검증으로 403 (association leak 차단)
    sid = uuid4()
    other_doc = MagicMock(user_id=uuid4())  # _REVIEWER_ID 아님
    create_uc, _, _ = _override_create_trio(app, sid=sid, created=None, doc=other_doc)
    _override_permission(app)

    client = TestClient(app)
    resp = client.post(
        "/api/v1/skills/personal",
        json={"name": "x", "description": "y", "source_document_id": str(uuid4())},
        headers=_headers(),
    )
    assert resp.status_code == 403
    create_uc.execute.assert_not_awaited()
    app.dependency_overrides.clear()


def test_create_personal_skill_with_tags_calls_update(app) -> None:
    sid = uuid4()
    created = _personal_skill(sid, _REVIEWER_ID)
    create_uc, update_uc, _ = _override_create_trio(app, sid=sid, created=created)
    _override_permission(app)

    client = TestClient(app)
    resp = client.post(
        "/api/v1/skills/personal",
        json={"name": "새 스킬", "description": "설명", "instructions": "## 지침", "tags": ["a", "b"]},
        headers=_headers(),
    )

    assert resp.status_code == 201
    assert create_uc.execute.await_args.kwargs["instructions"] == "## 지침"
    # tags 는 create 계약에 없어 생성 직후 update 로 반영.
    update_uc.execute.assert_awaited_once_with(
        skill_id=sid, actor_user_id=_REVIEWER_ID, name=None, description=None, tags=["a", "b"]
    )
    app.dependency_overrides.clear()


def test_create_personal_skill_missing_field_maps_422(app) -> None:
    _override_create_trio(app, sid=uuid4(), created=None)
    _override_permission(app)

    client = TestClient(app)
    resp = client.post("/api/v1/skills/personal", json={"name": "이름만"}, headers=_headers())
    assert resp.status_code == 422
    app.dependency_overrides.clear()


def test_create_personal_skill_requires_bearer(app) -> None:
    client = TestClient(app)
    resp = client.post("/api/v1/skills/personal", json={"name": "x", "description": "y"})
    assert resp.status_code == 401
