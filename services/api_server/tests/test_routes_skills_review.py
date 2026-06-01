"""POST /skills/{id}/submit + GET /skills/review-queue 라우트 테스트 (REQ-013).

검증축:
- submit: personal owner 게이트(GetPersonalSkill 선검증) 호출 + SubmitSkillUseCase 위임, action=submitted
- review-queue: ListReviewQueueUseCase에 actor_role 전달 + PersonalSkillResponse 매핑
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock

from app.dependencies.permission import get_permission_source
from app.dependencies.use_cases import (
    get_get_personal_skill_use_case,
    get_list_review_queue_use_case,
    get_submit_skill_use_case,
)
from app.routers.skills import router as skills_router
from common_schemas import PermissionSource
from fastapi import FastAPI
from fastapi.testclient import TestClient
from skills_marketplace.domain.entities.marketplace_personal_skill import MarketplacePersonalSkill
from skills_marketplace.domain.value_objects.skill_scope import SkillScope
from skills_marketplace.domain.value_objects.skill_state import SkillState

_USER_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
_SKILL_ID = uuid.UUID("44444444-4444-4444-4444-444444444444")


def _permission(role: str = "User") -> PermissionSource:
    return PermissionSource(
        user_id=_USER_ID,
        role=role,  # type: ignore[arg-type]
        department_id=uuid.uuid4(),
        session_id=uuid.uuid4(),
        granted_scopes=["Private"],
        risk_ceiling="High",
    )


def _make_app(*, permission: PermissionSource, submit=None, get_personal=None, review_queue=None) -> FastAPI:
    app = FastAPI()
    app.include_router(skills_router)
    app.dependency_overrides[get_permission_source] = lambda: permission
    if submit is not None:
        app.dependency_overrides[get_submit_skill_use_case] = lambda: submit
    if get_personal is not None:
        app.dependency_overrides[get_get_personal_skill_use_case] = lambda: get_personal
    if review_queue is not None:
        app.dependency_overrides[get_list_review_queue_use_case] = lambda: review_queue
    return app


def _review_skill() -> MarketplacePersonalSkill:
    now = datetime.now(UTC)
    return MarketplacePersonalSkill(
        skill_id=_SKILL_ID,
        owner_user_id=uuid.uuid4(),
        name="리뷰 대기 스킬",
        description="검토 요청됨",
        lifecycle_state=SkillState.REVIEW,
        created_at=now,
        updated_at=now,
    )


def test_submit_personal_owner_gated_and_delegates():
    submit = AsyncMock()
    get_personal = AsyncMock()  # owner 게이트 통과(예외 없음)
    app = _make_app(permission=_permission(), submit=submit, get_personal=get_personal)
    with TestClient(app) as tc:
        res = tc.post(f"/api/v1/skills/{_SKILL_ID}/submit", json={"scope": "personal"})
    assert res.status_code == 200
    assert res.json()["action"] == "submitted"
    # personal owner 게이트 선검증 + submit 위임
    get_personal.execute.assert_awaited_once_with(skill_id=_SKILL_ID, actor_user_id=_USER_ID)
    submit.execute.assert_awaited_once()
    assert submit.execute.call_args.kwargs["scope"] == SkillScope.PERSONAL


def test_review_queue_passes_actor_role_and_maps():
    review_queue = AsyncMock()
    review_queue.execute.return_value = [_review_skill()]
    app = _make_app(permission=_permission(role="Admin"), review_queue=review_queue)
    with TestClient(app) as tc:
        res = tc.get("/api/v1/skills/review-queue")
    assert res.status_code == 200
    body = res.json()
    assert len(body) == 1
    assert body[0]["lifecycle_state"] == "review"
    assert body[0]["skill_id"] == str(_SKILL_ID)
    assert review_queue.execute.call_args.kwargs["actor_role"] == "Admin"
