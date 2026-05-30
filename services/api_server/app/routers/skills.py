"""Skills Marketplace 게시 lifecycle + personal 미리보기/편집 라우트 (ADR-0020 Q4 + REQ-013).

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

Personal CRUD(REQ-013, 가원 요청): `GET /personal`, `GET/PUT/DELETE /personal/{id}`.
인가는 use case(Get/Update/Delete)가 owner 검사 + DRAFT-only 제약을 수행한다.
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from common_schemas import PermissionSource
from common_schemas.enums import RiskLevel
from fastapi import APIRouter, Depends, Query, Response, status
from pydantic import BaseModel, Field
from skills_marketplace.application.use_cases import (
    ApproveSkillUseCase,
    CreateDraftSkillUseCase,
    DeletePersonalSkillUseCase,
    GetPersonalSkillUseCase,
    ListUserPersonalSkillsUseCase,
    PublishSkillUseCase,
    UpdatePersonalSkillUseCase,
)
from skills_marketplace.domain.entities.marketplace_personal_skill import MarketplacePersonalSkill
from skills_marketplace.domain.value_objects.node_spec_staging import NodeSpecStaging
from skills_marketplace.domain.value_objects.skill_scope import SkillScope
from skills_marketplace.domain.value_objects.skill_state import SkillState

from app.dependencies.permission import get_permission_source
from app.dependencies.use_cases import (
    get_approve_skill_use_case,
    get_create_draft_skill_use_case,
    get_delete_personal_skill_use_case,
    get_get_personal_skill_use_case,
    get_list_personal_skills_use_case,
    get_publish_skill_use_case,
    get_update_personal_skill_use_case,
)

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


# ── Personal skills CRUD (REQ-013) ───────────────────────────────────────────

# embedding(768d Vector — 응답 비대화)·metadata·node_spec_staging(시스템 내부)는
# 응답에 노출하지 않는다. node_definition_id는 PUBLISHED 시점 프론트가 NodeDefinition을
# 따라가는 데 필요해 포함.
class PersonalSkillResponse(BaseModel):
    skill_id: UUID
    owner_user_id: UUID
    name: str
    description: str
    node_definition_id: UUID | None = None
    lifecycle_state: SkillState
    skill_document_uri: str | None = None
    workflow_id: UUID | None = None
    tags: list[str]
    version: str
    promoted_to_team_id: UUID | None = None
    created_at: datetime
    updated_at: datetime


def _to_response(skill: MarketplacePersonalSkill) -> PersonalSkillResponse:
    return PersonalSkillResponse(
        skill_id=skill.skill_id,
        owner_user_id=skill.owner_user_id,
        name=skill.name,
        description=skill.description,
        node_definition_id=skill.node_definition_id,
        lifecycle_state=SkillState(skill.lifecycle_state),
        skill_document_uri=skill.skill_document_uri,
        workflow_id=skill.workflow_id,
        tags=list(skill.tags),
        version=skill.version,
        promoted_to_team_id=skill.promoted_to_team_id,
        created_at=skill.created_at,
        updated_at=skill.updated_at,
    )


class UpdatePersonalSkillRequest(BaseModel):
    # 셋 다 Optional — 부분 수정. tags=[]는 "전체 비움"으로 해석(use case 정책과 일관).
    name: str | None = None
    description: str | None = None
    tags: list[str] | None = None


class CreatePersonalSkillRequest(BaseModel):
    name: str
    description: str
    instructions: str | None = None
    tags: list[str] = Field(default_factory=list)


@router.post("/personal", response_model=PersonalSkillResponse, status_code=status.HTTP_201_CREATED)
async def create_personal_skill(
    body: CreatePersonalSkillRequest,
    permission: PermissionSource = Depends(get_permission_source),
    create_use_case: CreateDraftSkillUseCase = Depends(get_create_draft_skill_use_case),
    update_use_case: UpdatePersonalSkillUseCase = Depends(get_update_personal_skill_use_case),
    get_use_case: GetPersonalSkillUseCase = Depends(get_get_personal_skill_use_case),
) -> PersonalSkillResponse:
    """개인 DRAFT 스킬 생성 — 스킬빌더 폼 입구 (REQ-010, 프론트 POST /skills/personal 대응).

    `CreateDraftSkillUseCase`(박아름, ADR-0020 ②e) 재사용. 이 use case는 본래 Skills Builder
    Agent(REQ-004 ③) 추출 결과용이라 `node_spec_staging`이 필수 입력이다. 수동 폼 생성은 노드
    스펙이 없어 빈 staging(action/빈 스키마/LOW)을 placeholder로 넣는다 — 실제 스펙은 추후
    에이전트 추출/publish 단계에서 확정. tags는 create 계약에 없어 생성 직후 update로 반영
    (owner+DRAFT 보장 — 방금 생성분). 응답은 GetPersonalSkill로 재조회해 일관 직렬화.
    """
    skill_id = await create_use_case.execute(
        owner_user_id=permission.user_id,
        name=body.name,
        description=body.description,
        node_spec_staging=NodeSpecStaging(
            category="action",
            input_schema={},
            output_schema={},
            risk_level=RiskLevel.LOW,
        ),
        instructions=body.instructions,
    )
    if body.tags:
        await update_use_case.execute(
            skill_id=skill_id,
            actor_user_id=permission.user_id,
            name=None,
            description=None,
            tags=body.tags,
        )
    created = await get_use_case.execute(skill_id=skill_id, actor_user_id=permission.user_id)
    return _to_response(created)


@router.get("/personal", response_model=list[PersonalSkillResponse])
async def list_personal_skills(
    lifecycle_state: SkillState | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    permission: PermissionSource = Depends(get_permission_source),
    use_case: ListUserPersonalSkillsUseCase = Depends(get_list_personal_skills_use_case),
) -> list[PersonalSkillResponse]:
    """현재 사용자(PermissionSource.user_id)의 개인 스킬 목록 — 미리보기 UI.

    스코프는 user_id로 보장(타인 스킬 노출 없음). `lifecycle_state` 미지정 시 전체 상태.
    """
    skills = await use_case.execute(
        user_id=permission.user_id,
        lifecycle_state=lifecycle_state,
        limit=limit,
        offset=offset,
    )
    return [_to_response(s) for s in skills]


@router.get("/personal/{skill_id}", response_model=PersonalSkillResponse)
async def get_personal_skill(
    skill_id: UUID,
    permission: PermissionSource = Depends(get_permission_source),
    use_case: GetPersonalSkillUseCase = Depends(get_get_personal_skill_use_case),
) -> PersonalSkillResponse:
    """개인 스킬 단건 조회 — owner만(use case가 AuthorizationError → 403). lifecycle 제약 없음."""
    skill = await use_case.execute(skill_id=skill_id, actor_user_id=permission.user_id)
    return _to_response(skill)


@router.put("/personal/{skill_id}", response_model=PersonalSkillResponse)
async def update_personal_skill(
    skill_id: UUID,
    body: UpdatePersonalSkillRequest,
    permission: PermissionSource = Depends(get_permission_source),
    use_case: UpdatePersonalSkillUseCase = Depends(get_update_personal_skill_use_case),
) -> PersonalSkillResponse:
    """개인 스킬 메타 수정 — owner + DRAFT only. 변경 없으면 use case가 현재 스킬 반환."""
    updated = await use_case.execute(
        skill_id=skill_id,
        actor_user_id=permission.user_id,
        name=body.name,
        description=body.description,
        tags=body.tags,
    )
    return _to_response(updated)


@router.delete("/personal/{skill_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_personal_skill(
    skill_id: UUID,
    permission: PermissionSource = Depends(get_permission_source),
    use_case: DeletePersonalSkillUseCase = Depends(get_delete_personal_skill_use_case),
) -> Response:
    """개인 스킬 삭제 — owner + DRAFT only. use case가 GCS SKILL.md → DB row 순으로 정리."""
    await use_case.execute(skill_id=skill_id, actor_user_id=permission.user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
