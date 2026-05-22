"""Skills Marketplace 게시 lifecycle 라우트 (ADR-0020 Q4).

scope-aware lifecycle 전이를 api_server(Composition Root)에서 skills_marketplace
use case로 위임한다. 전이 자체는 도메인 service(`SkillLifecycle`)가 수행하며,
라우트는 인증·요청 검증·use case 조립만 담당한다.

게시 lifecycle: DRAFT → (submit) REVIEW → (approve) APPROVED → (publish) PUBLISHED.
submit(DRAFT→REVIEW) 라우트는 대응 use case(`SubmitSkillUseCase`)가 skills_marketplace
(REQ-013)에 아직 없어 보류 — use case 신설 후 본 라우터에 추가한다.

인가(authorization) 미적용 — 추적 항목: 본 라우터는 인증만 강제하고 scope/소유권 기반
인가는 두지 않는다. `Admin` role은 서비스 운영자 전용이라, 스킬 거버넌스의 정당한 행위자
(personal=소유자 본인, team/company=구성원)는 모두 `User` — 라우트 레벨 role 가드가
성립하지 않는다. 올바른 인가는 스킬 로드 + 멤버십 판정이 필요한 도메인 로직이므로
`Approve/PublishSkillUseCase`(skills_marketplace) 내부 enforcement로 다룬다
(ADR-0020 후속, REQ-013 — 박아름).
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
    """게시 승인 — REVIEW → APPROVED (반려 시 DRAFT). 결정은 ApprovalWorkflow로 감사 기록."""
    await use_case.execute(
        skill_id=skill_id,
        scope=body.scope,
        reviewer_id=permission.user_id,
        approved=body.approved,
        comment=body.comment,
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
    # 미사용이지만 유지 — AuthMiddleware는 JWT만 검증, get_permission_source가
    # 세션 revoke·사용자 비활성 검사를 수행한다 (제거 시 stale 세션 publish 허용).
    _permission: PermissionSource = Depends(get_permission_source),
    use_case: PublishSkillUseCase = Depends(get_publish_skill_use_case),
) -> LifecycleResponse:
    """게시 확정 — APPROVED → PUBLISHED. node_spec_staging → NodeDefinition 생성·연결."""
    await use_case.execute(skill_id=skill_id, scope=body.scope)
    return LifecycleResponse(skill_id=skill_id, scope=body.scope, action="published")
