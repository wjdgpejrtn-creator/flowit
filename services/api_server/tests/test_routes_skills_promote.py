"""POST /skills/{id}/promote + GET /skills/review-queue?scope= 라우트 테스트 (REQ-013 승격 흐름).

검증축:
- promote personal→team: owner 게이트 + PromoteToTeam(team_id=department_id) + Submit(team) 위임,
  action=promotion_requested / scope=team / 결과는 새 스킬 id
- promote team→company: PromoteToCompany + Submit(company) 위임
- promote: department_id 없으면 400
- review-queue scope: actor_role/scope를 use case에 전달 + ReviewQueueItem 매핑
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock

from app.dependencies.permission import get_permission_source
from app.dependencies.use_cases import (
    get_get_personal_skill_use_case,
    get_list_review_queue_use_case,
    get_promote_to_company_use_case,
    get_promote_to_team_use_case,
    get_submit_skill_use_case,
)
from app.routers.skills import router as skills_router
from common_schemas import PermissionSource
from fastapi import FastAPI
from fastapi.testclient import TestClient
from skills_marketplace.domain.entities.marketplace_team_skill import MarketplaceTeamSkill
from skills_marketplace.domain.value_objects.skill_scope import SkillScope
from skills_marketplace.domain.value_objects.skill_state import SkillState

_USER_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
_DEPT_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")
_SKILL_ID = uuid.UUID("33333333-3333-3333-3333-333333333333")
_NEW_TEAM_ID = uuid.UUID("44444444-4444-4444-4444-444444444444")
_NEW_COMPANY_ID = uuid.UUID("55555555-5555-5555-5555-555555555555")


def _permission(role: str = "User") -> PermissionSource:
    return PermissionSource(
        user_id=_USER_ID,
        role=role,  # type: ignore[arg-type]
        department_id=_DEPT_ID,
        session_id=uuid.uuid4(),
        granted_scopes=["Private"],
        risk_ceiling="High",
    )


def _make_app(
    *,
    permission: PermissionSource | None = None,
    promote_team=None,
    promote_company=None,
    submit=None,
    get_personal=None,
    review_queue=None,
) -> FastAPI:
    app = FastAPI()
    app.include_router(skills_router)
    app.dependency_overrides[get_permission_source] = lambda: permission or _permission()
    # promote 라우트는 두 promote use case를 모두 Depends로 해석하므로(경로와 무관) 전부 오버라이드해
    # 실 DI(DB 세션) 접근을 차단한다. 미지정 시 기본 AsyncMock.
    pt = promote_team if promote_team is not None else AsyncMock()
    pc = promote_company if promote_company is not None else AsyncMock()
    sub = submit if submit is not None else AsyncMock()
    gp = get_personal if get_personal is not None else AsyncMock()
    app.dependency_overrides[get_promote_to_team_use_case] = lambda: pt
    app.dependency_overrides[get_promote_to_company_use_case] = lambda: pc
    app.dependency_overrides[get_submit_skill_use_case] = lambda: sub
    app.dependency_overrides[get_get_personal_skill_use_case] = lambda: gp
    if review_queue is not None:
        app.dependency_overrides[get_list_review_queue_use_case] = lambda: review_queue
    return app


def test_promote_personal_to_team_gates_owner_and_submits():
    promote_team = AsyncMock()
    promote_team.execute.return_value = _NEW_TEAM_ID
    submit = AsyncMock()
    get_personal = AsyncMock()  # owner 게이트 통과
    app = _make_app(promote_team=promote_team, submit=submit, get_personal=get_personal)
    with TestClient(app) as tc:
        res = tc.post(f"/api/v1/skills/{_SKILL_ID}/promote", json={"from_scope": "personal"})
    assert res.status_code == 200
    body = res.json()
    assert body["action"] == "promotion_requested"
    assert body["scope"] == "team"
    assert body["skill_id"] == str(_NEW_TEAM_ID)
    # owner 선검증 + team_id=department_id로 승격 + 새 스킬을 REVIEW로 submit
    get_personal.execute.assert_awaited_once_with(skill_id=_SKILL_ID, actor_user_id=_USER_ID)
    promote_team.execute.assert_awaited_once_with(personal_skill_id=_SKILL_ID, team_id=_DEPT_ID)
    submit.execute.assert_awaited_once()
    assert submit.execute.call_args.kwargs["skill_id"] == _NEW_TEAM_ID
    assert submit.execute.call_args.kwargs["scope"] == SkillScope.TEAM


def test_promote_team_to_company_submits():
    promote_company = AsyncMock()
    promote_company.execute.return_value = _NEW_COMPANY_ID
    submit = AsyncMock()
    app = _make_app(promote_company=promote_company, submit=submit)
    with TestClient(app) as tc:
        res = tc.post(f"/api/v1/skills/{_SKILL_ID}/promote", json={"from_scope": "team"})
    assert res.status_code == 200
    body = res.json()
    assert body["scope"] == "company"
    assert body["skill_id"] == str(_NEW_COMPANY_ID)
    promote_company.execute.assert_awaited_once_with(team_skill_id=_SKILL_ID)
    assert submit.execute.call_args.kwargs["scope"] == SkillScope.COMPANY


def test_promote_company_rejected_400():
    app = _make_app()
    with TestClient(app) as tc:
        res = tc.post(f"/api/v1/skills/{_SKILL_ID}/promote", json={"from_scope": "company"})
    assert res.status_code == 400


def _team_review_skill() -> MarketplaceTeamSkill:
    now = datetime.now(UTC)
    return MarketplaceTeamSkill(
        skill_id=_NEW_TEAM_ID,
        team_id=_DEPT_ID,
        author_id=_USER_ID,
        name="승격 요청 팀 스킬",
        description="personal에서 승격됨",
        lifecycle_state=SkillState.REVIEW,
        created_at=now,
        updated_at=now,
    )


def test_review_queue_team_scope_passes_scope_and_maps():
    review_queue = AsyncMock()
    review_queue.execute.return_value = [_team_review_skill()]
    app = _make_app(permission=_permission(role="Admin"), review_queue=review_queue)
    with TestClient(app) as tc:
        res = tc.get("/api/v1/skills/review-queue?scope=team")
    assert res.status_code == 200
    body = res.json()
    assert len(body) == 1
    assert body[0]["scope"] == "team"
    assert body[0]["skill_id"] == str(_NEW_TEAM_ID)
    assert body[0]["lifecycle_state"] == "review"
    # team/company 엔티티엔 owner_user_id가 없어 None
    assert body[0]["owner_user_id"] is None
    assert review_queue.execute.call_args.kwargs["actor_role"] == "Admin"
    assert review_queue.execute.call_args.kwargs["scope"] == SkillScope.TEAM
