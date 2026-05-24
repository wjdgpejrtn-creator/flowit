"""Skills Marketplace 게시 lifecycle 라우트 (ADR-0020 Q4).

scope-aware lifecycle 전이를 api_server(Composition Root)에서 skills_marketplace
use case로 위임한다. 전이 자체는 도메인 service(`SkillLifecycle`)가 수행하며,
라우트는 인증·요청 검증·use case 조립만 담당한다.

게시 lifecycle: DRAFT → (submit) REVIEW → (approve) APPROVED → (publish) PUBLISHED.
submit(DRAFT→REVIEW) 라우트는 대응 use case(`SubmitSkillUseCase`)가 skills_marketplace
(REQ-013)에 아직 없어 보류 — use case 신설 후 본 라우터에 추가한다.

인가(authorization): `Approve/PublishSkillUseCase`가 `SkillApprovalPolicy`로 scope별
인가를 enforce한다(ADR-0020 위임2, PR #158). 본 라우트는 인증된 `PermissionSource`에서
actor 정보(`user_id`/`role`/`department_id`)를 use case로 전달만 한다 — 정책 판정은
도메인 책임. 정책: Admin=전체 / personal=owner 본인 / team=`team_manager`+`department_id`
매칭 / company=`company_manager`. 위반 시 `AuthorizationError` → 403(E-PERM-001/002).
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from common_schemas import PermissionSource
from skills_marketplace.application.use_cases import ApproveSkillUseCase, PublishSkillUseCase
from skills_marketplace.domain.value_objects.skill_scope import SkillScope

from app.dependencies.permission import get_permission_source
from app.dependencies.use_cases import get_approve_skill_use_case, get_publish_skill_use_case

router = APIRouter(prefix="/api/v1/skills", tags=["skills"])


class ApproveSkillRequest(BaseModel):
    scope: SkillScope
    approved: bool
    comment: str | None = None


class PublishSkillRequest(BaseModel):
    scope: SkillScope


class LifecycleResponse(BaseModel):
    skill_id: UUID
    scope: SkillScope
    action: str


@router.post("/{skill_id}/approve", response_model=LifecycleResponse)
async def approve_skill(
    skill_id: UUID,
    body: ApproveSkillRequest,
    permission: PermissionSource = Depends(get_permission_source),
    use_case: ApproveSkillUseCase = Depends(get_approve_skill_use_case),
) -> LifecycleResponse:
    """게시 승인 — REVIEW → APPROVED (반려 시 DRAFT). 결정은 ApprovalWorkflow로 감사 기록.

    scope별 인가는 `SkillApprovalPolicy`가 use case 내부에서 수행(ADR-0020 위임2).
    """
    await use_case.execute(
        skill_id=skill_id,
        scope=body.scope,
        reviewer_id=permission.user_id,
        approved=body.approved,
        comment=body.comment,
        actor_role=permission.role,
        actor_department_id=permission.department_id,
    )
    return LifecycleResponse(
        skill_id=skill_id,
        scope=body.scope,
        action="approved" if body.approved else "rejected",
    )


@router.post("/{skill_id}/publish", response_model=LifecycleResponse)
async def publish_skill(
    skill_id: UUID,
    body: PublishSkillRequest,
    permission: PermissionSource = Depends(get_permission_source),
    use_case: PublishSkillUseCase = Depends(get_publish_skill_use_case),
) -> LifecycleResponse:
    """게시 확정 — APPROVED → PUBLISHED. node_spec_staging → NodeDefinition 생성·연결.

    scope별 인가는 `SkillApprovalPolicy`가 use case 내부에서 수행(ADR-0020 위임2).
    """
    await use_case.execute(
        skill_id=skill_id,
        scope=body.scope,
        actor_user_id=permission.user_id,
        actor_role=permission.role,
        actor_department_id=permission.department_id,
    )
    return LifecycleResponse(skill_id=skill_id, scope=body.scope, action="published")
