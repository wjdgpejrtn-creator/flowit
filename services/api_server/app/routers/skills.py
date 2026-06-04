"""Skills Marketplace 게시 lifecycle + personal 미리보기/편집 라우트 (ADR-0020 Q4 + REQ-013).

scope-aware lifecycle 전이를 api_server(Composition Root)에서 skills_marketplace
use case로 위임한다. 전이 자체는 도메인 service(`SkillLifecycle`)가 수행하며,
라우트는 인증·요청 검증·use case 조립만 담당한다.

게시 lifecycle: DRAFT → (submit) REVIEW → (approve) APPROVED → (publish) PUBLISHED.
submit(DRAFT→REVIEW)은 `POST /{skill_id}/submit`(owner가 리뷰 요청), 관리자는
`GET /review-queue`(REVIEW 모아보기, Admin only) → approve/publish로 처리한다.

인가(authorization): `Approve/PublishSkillUseCase`가 `SkillApprovalPolicy`로 scope별
인가를 enforce한다(ADR-0020 위임2, PR #158). 본 라우트는 인증된 `PermissionSource`에서
actor 정보(`user_id`/`role`/`department_id`)를 use case로 전달만 한다 — 정책 판정은
도메인 책임. 정책: Admin=전체 / personal=owner 본인 / team=`team_manager`+`department_id`
매칭 / company=`company_manager`. 위반 시 `AuthorizationError` → 403(E-PERM-001/002).

Personal CRUD(REQ-013, 가원 요청): `GET /personal`, `GET/PUT/DELETE /personal/{id}`.
인가는 use case(Get/Update/Delete)가 owner 검사 + DRAFT-only 제약을 수행한다.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from uuid import UUID, uuid4

import httpx
from common_schemas import DocumentBlock, PermissionSource
from common_schemas.enums import RiskLevel
from doc_parser.domain.ports.repository_port import DocumentRepositoryPort
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, model_validator
from skills_marketplace.application.use_cases import (
    ApproveSkillUseCase,
    CreateDraftSkillUseCase,
    DeletePersonalSkillUseCase,
    GetMarketplaceSkillDocumentUseCase,
    GetMarketplaceSkillUseCase,
    GetPersonalSkillDocumentUseCase,
    GetPersonalSkillUseCase,
    ListMarketplaceSkillsUseCase,
    ListReviewQueueUseCase,
    ListUserPersonalSkillsUseCase,
    PromoteToCompanyUseCase,
    PromoteToTeamUseCase,
    PublishSkillUseCase,
    SubmitSkillUseCase,
    UpdatePersonalSkillUseCase,
)
from skills_marketplace.domain.entities.marketplace_company_skill import MarketplaceCompanySkill
from skills_marketplace.domain.entities.marketplace_personal_skill import MarketplacePersonalSkill
from skills_marketplace.domain.entities.marketplace_team_skill import MarketplaceTeamSkill
from skills_marketplace.domain.value_objects.node_spec_staging import NodeSpecStaging
from skills_marketplace.domain.value_objects.skill_scope import SkillScope
from skills_marketplace.domain.value_objects.skill_state import SkillState

from app.dependencies.clients import get_skills_builder_http
from app.dependencies.permission import get_permission_source
from app.dependencies.repositories import get_document_repository
from app.dependencies.use_cases import (
    get_approve_skill_use_case,
    get_create_draft_skill_use_case,
    get_delete_personal_skill_use_case,
    get_get_marketplace_skill_document_use_case,
    get_get_marketplace_skill_use_case,
    get_get_personal_skill_document_use_case,
    get_get_personal_skill_use_case,
    get_list_marketplace_skills_use_case,
    get_list_personal_skills_use_case,
    get_list_review_queue_use_case,
    get_promote_to_company_use_case,
    get_promote_to_team_use_case,
    get_publish_skill_use_case,
    get_submit_skill_use_case,
    get_update_personal_skill_use_case,
)
from app.services.skill_templates import (
    SkillTemplate,
    list_templates,
    synthesize_sop_document,
)
from app.sse_proxy import SSE_HEADERS, unwrap_agent_sse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/skills", tags=["skills"])


class ApproveSkillRequest(BaseModel):
    scope: SkillScope
    approved: bool
    comment: str | None = None


class PublishSkillRequest(BaseModel):
    scope: SkillScope


class SubmitSkillRequest(BaseModel):
    scope: SkillScope


class PromoteSkillRequest(BaseModel):
    # 승격 출발 scope — personal→team, team→company (company는 최상위라 승격 불가).
    from_scope: SkillScope


class LifecycleResponse(BaseModel):
    skill_id: UUID
    scope: SkillScope
    action: str


@router.post("/{skill_id}/submit", response_model=LifecycleResponse)
async def submit_skill(
    skill_id: UUID,
    body: SubmitSkillRequest,
    permission: PermissionSource = Depends(get_permission_source),
    use_case: SubmitSkillUseCase = Depends(get_submit_skill_use_case),
    get_personal_use_case: GetPersonalSkillUseCase = Depends(get_get_personal_skill_use_case),
) -> LifecycleResponse:
    """리뷰 요청 — DRAFT → REVIEW (owner가 본인 스킬을 검토 큐에 올린다).

    personal scope는 owner 본인만 제출 가능 — `GetPersonalSkillUseCase`로 소유/존재를 먼저 검증한다
    (타인 DRAFT를 제출하는 것 차단, 미존재 404 / 비소유 403). 전이 자체의 상태 가드(DRAFT만 REVIEW로)는
    `SubmitSkillUseCase`(`SkillLifecycle.transition`)가 수행 — DRAFT 외 상태면 도메인 전이 오류.
    team/company scope의 제출 권한 정책은 후속(현재 승인 단계에서 manager 인가로 보호).
    """
    if body.scope == SkillScope.PERSONAL:
        # owner 게이트(+ 존재 검증). use case는 actor를 모르므로 라우트(composition root)가 선검증.
        await get_personal_use_case.execute(skill_id=skill_id, actor_user_id=permission.user_id)
    await use_case.execute(skill_id=skill_id, scope=body.scope)
    return LifecycleResponse(skill_id=skill_id, scope=body.scope, action="submitted")


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


@router.post("/{skill_id}/promote", response_model=LifecycleResponse)
async def promote_skill(
    skill_id: UUID,
    body: PromoteSkillRequest,
    permission: PermissionSource = Depends(get_permission_source),
    promote_team_use_case: PromoteToTeamUseCase = Depends(get_promote_to_team_use_case),
    promote_company_use_case: PromoteToCompanyUseCase = Depends(get_promote_to_company_use_case),
    submit_use_case: SubmitSkillUseCase = Depends(get_submit_skill_use_case),
    get_personal_use_case: GetPersonalSkillUseCase = Depends(get_get_personal_skill_use_case),
) -> LifecycleResponse:
    """승격 요청 — 하위 scope 스킬을 상위 scope로 복제(재심사 리셋) 후 REVIEW로 올린다 (REQ-013).

    - `from_scope=personal` → **team** 승격: 요청자 본인 소유 personal만(`GetPersonalSkillUseCase`로
      소유/존재 선검증, 타인 스킬 차단 404/403). `PromoteToTeam`이 team_id=요청자 부서(`department_id`)로
      새 team 스킬을 DRAFT 복제.
    - `from_scope=team` → **company** 승격: `PromoteToCompany`가 새 company 스킬을 DRAFT 복제.
      (team 스킬 승격 권한 정책은 후속 — submit/promote 단계 게이트는 #289 follow-up과 동일선상.)

    승격은 상위 scope에 새 스킬을 **DRAFT**로 만든다(게시상태 비승계 — 조장 리뷰 #98). 이어서
    `SubmitSkillUseCase`로 **REVIEW** 전이해 관리자 리뷰 큐(`GET /review-queue?scope=team|company`)에
    노출 → 관리자가 `approve` → `publish`로 처리한다. 원본(하위 scope)은 그대로 두고 새 스킬만 심사한다.
    """
    if body.from_scope == SkillScope.PERSONAL:
        # 본인 소유 personal만 승격 — submit과 동일한 owner 게이트(미존재 404 / 비소유 403).
        await get_personal_use_case.execute(skill_id=skill_id, actor_user_id=permission.user_id)
        new_skill_id = await promote_team_use_case.execute(
            personal_skill_id=skill_id, team_id=permission.department_id
        )
        target_scope = SkillScope.TEAM
    elif body.from_scope == SkillScope.TEAM:
        new_skill_id = await promote_company_use_case.execute(team_skill_id=skill_id)
        target_scope = SkillScope.COMPANY
    else:
        raise HTTPException(status_code=400, detail="company 스킬은 더 승격할 수 없습니다")

    # 승격 결과(DRAFT)를 관리자 리뷰 큐에 노출 — REVIEW로 전이.
    # promote(save)와 submit(save)은 같은 request-scoped 세션을 공유하고(get_db Depends 캐시),
    # 커밋은 핸들러 정상 종료 시 1회뿐(repo는 flush만). 따라서 submit이 실패해 라우트가 raise하면
    # get_db가 rollback해 **promote의 DRAFT도 함께 롤백**된다 — orphan DRAFT/중복 누적 없음(원자적).
    await submit_use_case.execute(skill_id=new_skill_id, scope=target_scope)
    return LifecycleResponse(
        skill_id=new_skill_id, scope=target_scope, action="promotion_requested"
    )


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
    source_document_id: UUID | None = None  # REQ-010 기반 문서 association
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
        source_document_id=skill.source_document_id,
        tags=list(skill.tags),
        version=skill.version,
        promoted_to_team_id=skill.promoted_to_team_id,
        created_at=skill.created_at,
        updated_at=skill.updated_at,
    )


class UpdatePersonalSkillRequest(BaseModel):
    # 넷 다 Optional — 부분 수정. tags=[]는 "전체 비움"으로 해석(use case 정책과 일관).
    # instructions = 지침서 SKILL.md 본문 — 주어지면 GCS에 재저장(ADR-0017 이중 저장).
    name: str | None = None
    description: str | None = None
    tags: list[str] | None = None
    instructions: str | None = None


class CreatePersonalSkillRequest(BaseModel):
    name: str
    description: str
    instructions: str | None = None
    tags: list[str] = Field(default_factory=list)
    # REQ-010 문서→빌더 핸드오프: 기반 문서 association. None=직접 진입.
    source_document_id: UUID | None = None
    # 추출 초안의 노드 스펙(category/입출력/risk/연동). 있으면 publish 시 실제 NodeDefinition I/O가 된다.
    # None(수동 폼 / 미전달)이면 placeholder(action/빈 스키마/LOW)로 생성 — 기존 동작 유지(하위호환).
    node_spec_staging: NodeSpecStaging | None = None


@router.post("/personal", response_model=PersonalSkillResponse, status_code=status.HTTP_201_CREATED)
async def create_personal_skill(
    body: CreatePersonalSkillRequest,
    permission: PermissionSource = Depends(get_permission_source),
    create_use_case: CreateDraftSkillUseCase = Depends(get_create_draft_skill_use_case),
    update_use_case: UpdatePersonalSkillUseCase = Depends(get_update_personal_skill_use_case),
    get_use_case: GetPersonalSkillUseCase = Depends(get_get_personal_skill_use_case),
    doc_repo: DocumentRepositoryPort = Depends(get_document_repository),
) -> PersonalSkillResponse:
    """개인 DRAFT 스킬 생성 — 스킬빌더 폼 입구 (REQ-010, 프론트 POST /skills/personal 대응).

    `CreateDraftSkillUseCase`(박아름, ADR-0020 ②e) 재사용. 이 use case는 `node_spec_staging`이
    필수 입력이다 — `node_spec_staging`이 요청에 오면(추출 초안의 실 스펙) 그대로 보관하고, 없으면
    (수동 폼) placeholder(action/빈 스키마/LOW)를 넣는다. 이 staging이 publish 시 NodeDefinition의
    실제 입출력 스키마가 되므로, 추출 경로는 staging을 실어 보내야 워크플로우 노드 I/O가 채워진다.
    tags는 create 계약에 없어 생성 직후 update로 반영(owner+DRAFT 보장 — 방금 생성분).
    응답은 GetPersonalSkill로 재조회해 일관 직렬화.

    `source_document_id`(REQ-010 association)가 주어지면 create 전에 문서 존재+소유를 검증한다 —
    DB FK 위반에 맡기면 500이 되고(404/403이 정확), 타인 문서 id가 FK만 통과해 association되는
    것을 막는다. 검증은 composition root(라우터)의 책임 — skills_marketplace use case는 doc_parser를
    모르고(도메인 디커플), doc_parser GET /{id}와 동일한 404/403 패턴을 재사용한다.
    """
    if body.source_document_id is not None:
        document = await doc_repo.get_by_id(body.source_document_id)
        if document is None:
            raise HTTPException(status_code=404, detail=f"Document {body.source_document_id} not found")
        if document.user_id != permission.user_id:
            raise HTTPException(status_code=403, detail="Document belongs to another user")

    skill_id = await create_use_case.execute(
        owner_user_id=permission.user_id,
        name=body.name,
        description=body.description,
        # 추출 staging이 오면 그대로(실 I/O), 없으면 placeholder — publish 시 NodeDefinition 스펙이 된다.
        node_spec_staging=body.node_spec_staging
        or NodeSpecStaging(
            category="action",
            input_schema={},
            output_schema={},
            risk_level=RiskLevel.LOW,
        ),
        instructions=body.instructions,
        source_document_id=body.source_document_id,
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


# ── default 템플릿(seed) 노출 — 문서 없는 사용자용 위저드 재료 (위저드 재설계 Phase 0) ────


@router.get("/templates", response_model=list[SkillTemplate])
async def list_skill_templates(
    permission: PermissionSource = Depends(get_permission_source),
) -> list[SkillTemplate]:
    """default 위저드 카드 목록 — 업종 6 + 직무 5 seed 메타(code/name/description/kind).

    스킬빌더 첫 화면에서 "문서가 없어요 → 직접 만들게요"를 고른 사용자에게 보여줄 선택지.
    사용자가 카드를 고르면 `POST /skills/extract`에 `template_code`를 실어, 서버가 해당 seed를
    SOP 문서로 합성해 동일한 추출 위저드로 합류시킨다(skill-builder-wizard-redesign.md).
    seed 메타만 읽는 읽기 전용 — 인증 필수.
    """
    return list(list_templates())


# ── 문서/템플릿 → 스킬 자동 추출 (REQ-010/013, ADR-0020 Q8 wizard 1차) ──────────


class ExtractSkillRequest(BaseModel):
    """추출 재료 — `source_document_id`(내 문서) XOR `template_code`(default seed) 중 정확히 하나."""

    # 분석 완료된 SOP 문서 id — 본문(blocks)을 LLM에 넣어 SkillNode 초안을 추출한다.
    source_document_id: UUID | None = None
    # default 위저드 — 업종/직무 seed code. 서버가 seed를 SOP DocumentBlock으로 합성해 동일 경로 투입.
    template_code: str | None = None

    @model_validator(mode="after")
    def _exactly_one_source(self) -> ExtractSkillRequest:
        if (self.source_document_id is None) == (self.template_code is None):
            raise ValueError("source_document_id 또는 template_code 중 정확히 하나를 지정하세요")
        return self


@router.post("/extract")
async def extract_skill_from_document(
    body: ExtractSkillRequest,
    permission: PermissionSource = Depends(get_permission_source),
    doc_repo: DocumentRepositoryPort = Depends(get_document_repository),
    client: httpx.AsyncClient | None = Depends(get_skills_builder_http),
) -> StreamingResponse:
    """문서 또는 default 템플릿 → Skills Builder(metadata) → 메타 5필드 SSE 스트림 (저장 X, 검토용).

    스킬빌더 위저드 1단계(옵션 1 — 2단계 분리). 두 갈래는 **추출 입력(DocumentBlock)을 무엇으로
    만드느냐만** 다르고, skills-builder `/v1/agent/route`(`source_type="sop"`, `step="metadata"`)로
    **전체 DocumentBlock**을 전달하는 이후 경로는 동일. LLM이 추출한 SkillNode 메타 5필드
    (node_type/name/description/category/risk_level)를 SSE로 프록시한다 — inputs/outputs/
    instructions 등 토큰 무거운 detail은 `POST /extract/detail`로 분리(LLM JSON 잘림 해소).

    - `source_document_id`: 내 분석 완료 문서. 소유/존재/blocks 검증(404/403/409).
    - `template_code`: default seed(업종/직무). 서버가 seed→SOP DocumentBlock 합성(미존재 404).

    프레임: `agent_node`(진행) → `result`(payload.skill_metas 메타 목록) | `error`. 사용자가 카드
    그리드에서 1건 선택하면 frontend는 `POST /extract/detail`로 detail을 채워 폼에 prefill한다.
    """
    if client is None:
        raise HTTPException(
            status_code=503, detail="Skills Builder unavailable — SKILLS_BUILDER_URL 미설정"
        )

    document: DocumentBlock
    if body.template_code is not None:
        # default 위저드 — seed를 SOP 문서로 합성(영속 X). 미존재 template_code는 404.
        synthesized = synthesize_sop_document(body.template_code, permission.user_id)
        if synthesized is None:
            raise HTTPException(status_code=404, detail=f"Template '{body.template_code}' not found")
        document = synthesized
    else:
        # 문서 위저드 — 소유/존재 검증(doc_parser GET /{id}와 동일한 404/403 패턴, composition root 책임).
        document = await doc_repo.get_by_id(body.source_document_id)
        if document is None:
            raise HTTPException(status_code=404, detail=f"Document {body.source_document_id} not found")
        if document.user_id != permission.user_id:
            raise HTTPException(status_code=403, detail="Document belongs to another user")
        # blocks가 없으면 추출할 본문이 없음(분석 미완료/실패) — 추출 호출 전에 409로 빠르게 안내.
        if not document.blocks:
            raise HTTPException(
                status_code=409,
                detail="Document has no parsed blocks — 먼저 문서 분석을 완료하세요",
            )

    # AgentProtocolRequest 봉투(plain dict) — agents._build_agent_payload와 동일 패턴.
    # 수신 측 skills-builder(Modal)가 AgentProtocolRequest로 검증한다. state는 추출 경로에서
    # 쓰이지 않지만 스키마상 필수라 최소 형태로 채운다(orchestrator create_session과 동일).
    session_id = str(uuid4())
    user_id = str(permission.user_id)
    proxy_payload = {
        "session_id": session_id,
        "user_id": user_id,
        "personal_memory": [],
        "payload": {
            "source_type": "sop",
            "step": "metadata",
            "document": document.model_dump(mode="json"),
        },
        "state": {
            "session_id": session_id,
            "user_id": user_id,
            "messages": [],
            "turn_count": 0,
            "mode": "general",
            "execution_status": "pending",
            "node_candidates": [],
        },
    }

    async def generate():
        try:
            # timeout은 클라이언트 default(init_skills_builder_http가 settings.skills_builder_timeout_s로
            # 설정)에 위임 — per-request 오버라이드를 두면 SKILLS_BUILDER_TIMEOUT_S env가 무력화된다.
            async with client.stream(
                "POST", "/v1/agent/route", json=proxy_payload
            ) as resp:
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    for frame_line in unwrap_agent_sse(line[6:]):
                        yield frame_line
        except Exception as exc:
            logger.error("skills-builder extract 스트리밍 실패: %s", exc)
            err = {"frame_type": "error", "code": "E_PROXY", "message": str(exc)}
            yield f"data: {json.dumps(err)}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream", headers=SSE_HEADERS)


# ── 선택된 메타에 대한 detail 추출 (옵션 1 — 2단계 분리, LLM JSON 잘림 해소) ────────


class ExtractSkillDetailRequest(BaseModel):
    """detail 추출 재료 — `source_document_id`(내 문서) XOR `template_code`(default seed) 중 하나
    + 1차에서 받은 선택된 메타 5필드.
    """

    source_document_id: UUID | None = None
    template_code: str | None = None
    # 1차 extract 응답의 skill_metas[i] 그대로 (node_type/name/description/category/risk_level).
    meta: dict

    @model_validator(mode="after")
    def _exactly_one_source(self) -> ExtractSkillDetailRequest:
        if (self.source_document_id is None) == (self.template_code is None):
            raise ValueError("source_document_id 또는 template_code 중 정확히 하나를 지정하세요")
        return self

    @model_validator(mode="after")
    def _meta_required_keys(self) -> ExtractSkillDetailRequest:
        required = {"node_type", "name", "description", "category", "risk_level"}
        missing = required - set(self.meta.keys())
        if missing:
            raise ValueError(f"meta에 필수 필드 누락: {sorted(missing)}")
        return self


class ExtractSkillDetailResponse(BaseModel):
    """detail 응답 — frontend가 1차 메타와 합쳐 폼에 prefill."""

    skill_detail: dict


@router.post("/extract/detail", response_model=ExtractSkillDetailResponse)
async def extract_skill_detail(
    body: ExtractSkillDetailRequest,
    permission: PermissionSource = Depends(get_permission_source),
    doc_repo: DocumentRepositoryPort = Depends(get_document_repository),
    client: httpx.AsyncClient | None = Depends(get_skills_builder_http),
) -> ExtractSkillDetailResponse:
    """선택된 메타에 대한 detail(inputs/outputs/instructions/...) 추출 — JSON 단건 응답.

    옵션 1의 2차 호출: frontend가 1차 `POST /extract` 응답에서 받은 메타 1건을 선택해
    detail을 채우면 폼에 prefill한다. LLM 1회 호출이라 SSE 진행률 표시 의미 적어 JSON으로 반환.

    Stateless: source(document_id/template_code)와 meta를 다시 전달받는다 — 1차 결과를 서버에
    보관하지 않음(인프라 의존 회피, 인가 단순화).
    """
    if client is None:
        raise HTTPException(
            status_code=503, detail="Skills Builder unavailable — SKILLS_BUILDER_URL 미설정"
        )

    # source 검증/합성 — extract 라우트와 동일 정책(소유/존재/blocks).
    document: DocumentBlock
    if body.template_code is not None:
        synthesized = synthesize_sop_document(body.template_code, permission.user_id)
        if synthesized is None:
            raise HTTPException(status_code=404, detail=f"Template '{body.template_code}' not found")
        document = synthesized
    else:
        document = await doc_repo.get_by_id(body.source_document_id)
        if document is None:
            raise HTTPException(status_code=404, detail=f"Document {body.source_document_id} not found")
        if document.user_id != permission.user_id:
            raise HTTPException(status_code=403, detail="Document belongs to another user")
        if not document.blocks:
            raise HTTPException(
                status_code=409,
                detail="Document has no parsed blocks — 먼저 문서 분석을 완료하세요",
            )

    session_id = str(uuid4())
    user_id = str(permission.user_id)
    proxy_payload = {
        "session_id": session_id,
        "user_id": user_id,
        "personal_memory": [],
        "payload": {
            "source_type": "sop",
            "step": "detail",
            "document": document.model_dump(mode="json"),
            "meta": body.meta,
        },
        "state": {
            "session_id": session_id,
            "user_id": user_id,
            "messages": [],
            "turn_count": 0,
            "mode": "general",
            "execution_status": "pending",
            "node_candidates": [],
        },
    }

    # detail은 단일 ResultFrame이 핵심 — SSE envelope에서 result/error frame을 collect 후 JSON 반환.
    result_payload: dict | None = None
    error_frame: dict | None = None
    try:
        async with client.stream("POST", "/v1/agent/route", json=proxy_payload) as resp:
            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                try:
                    envelope = json.loads(line[6:])
                except json.JSONDecodeError:
                    continue
                for frame in envelope.get("frames", []):
                    if frame.get("frame_type") == "result":
                        result_payload = frame.get("payload")
                    elif frame.get("frame_type") == "error":
                        error_frame = frame
    except Exception as exc:
        logger.error("skills-builder extract/detail 호출 실패: %s", exc)
        raise HTTPException(status_code=502, detail=f"Skills Builder 호출 실패: {exc}") from exc

    if error_frame is not None:
        # LLM/입력 검증 실패 — 422로 매핑(클라이언트 입력 또는 LLM 응답 문제).
        raise HTTPException(
            status_code=422,
            detail={"code": error_frame.get("code"), "message": error_frame.get("message")},
        )

    if result_payload is None or "skill_detail" not in result_payload:
        raise HTTPException(status_code=502, detail="Skills Builder가 detail 응답을 반환하지 않음")

    return ExtractSkillDetailResponse(skill_detail=result_payload["skill_detail"])


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


# 리뷰 큐 항목 — personal/team/company 공통 표현(관리자 승인 페이지용). owner_user_id는 personal만
# (team/company 엔티티엔 없어 None). scope로 어느 탭의 승격 요청인지 구분.
class ReviewQueueItemResponse(BaseModel):
    skill_id: UUID
    scope: SkillScope
    name: str
    description: str
    lifecycle_state: SkillState
    owner_user_id: UUID | None = None
    tags: list[str]
    version: str
    created_at: datetime
    updated_at: datetime


def _to_review_item(
    skill: MarketplacePersonalSkill | MarketplaceTeamSkill | MarketplaceCompanySkill,
    scope: SkillScope,
) -> ReviewQueueItemResponse:
    return ReviewQueueItemResponse(
        skill_id=skill.skill_id,
        scope=scope,
        name=skill.name,
        description=skill.description,
        lifecycle_state=SkillState(skill.lifecycle_state),
        owner_user_id=getattr(skill, "owner_user_id", None),
        tags=list(skill.tags),
        version=skill.version,
        created_at=skill.created_at,
        updated_at=skill.updated_at,
    )


@router.get("/review-queue", response_model=list[ReviewQueueItemResponse])
async def list_review_queue(
    scope: SkillScope = Query(
        default=SkillScope.PERSONAL, description="personal | team | company"
    ),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    permission: PermissionSource = Depends(get_permission_source),
    use_case: ListReviewQueueUseCase = Depends(get_list_review_queue_use_case),
) -> list[ReviewQueueItemResponse]:
    """관리자 리뷰 큐 — REVIEW 상태로 올라온 스킬을 scope별로 모아 본다 (REQ-013).

    - `scope=personal`(기본): owner가 `POST /{id}/submit`으로 올린 개인 스킬 리뷰 요청.
    - `scope=team|company`: 하위 scope에서 `POST /{id}/promote`로 승격 요청(promote→submit)되어
      REVIEW로 올라온 스킬.

    인가는 use case가 enforce — **Admin role만** 허용(비-Admin은 `AuthorizationError` → 403).
    관리자는 항목별로 `POST /{id}/approve` → `POST /{id}/publish`(2단계)로 처리한다.
    """
    skills = await use_case.execute(
        actor_role=permission.role, scope=scope, limit=limit, offset=offset
    )
    return [_to_review_item(s, scope) for s in skills]


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
    """개인 스킬 수정 — owner only(상태 무관, 게시 스킬도 수정 가능). 변경 없으면 현재 스킬 반환.

    `name`/`description`/`tags`(메타) + `instructions`(SKILL.md 본문)를 부분 수정한다. instructions가
    오면 use case가 GCS에 SKILL.md를 재저장한다(ADR-0017). ⚠️ 검색 임베딩은 재계산하지 않는다(후속).
    """
    updated = await use_case.execute(
        skill_id=skill_id,
        actor_user_id=permission.user_id,
        name=body.name,
        description=body.description,
        tags=body.tags,
        instructions=body.instructions,
    )
    return _to_response(updated)


# instructions = SKILL.md markdown 본문(지침서). 마켓플레이스 응답과 동형 — personal 상세 본문 노출용.
class PersonalSkillDocumentResponse(BaseModel):
    skill_id: UUID
    name: str
    description: str
    instructions: str


@router.get("/personal/{skill_id}/document", response_model=PersonalSkillDocumentResponse)
async def get_personal_skill_document(
    skill_id: UUID,
    permission: PermissionSource = Depends(get_permission_source),
    use_case: GetPersonalSkillDocumentUseCase = Depends(get_get_personal_skill_document_use_case),
) -> PersonalSkillDocumentResponse:
    """개인 스킬 지침서(SKILL.md) 본문 — 상세 페이지가 메타 조회 후 lazy-load.

    owner 게이트만 적용(use case) — owner는 미게시 DRAFT 본문도 미리보기/편집할 수 있다(마켓플레이스
    document와 달리 lifecycle 무관). 지침서가 GCS에 없으면(수동 생성 등) 404 → 프론트 graceful 처리.
    """
    document = await use_case.execute(skill_id=skill_id, actor_user_id=permission.user_id)
    return PersonalSkillDocumentResponse(
        skill_id=document.skill_id,
        name=document.name,
        description=document.description,
        instructions=document.instructions,
    )


@router.delete("/personal/{skill_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_personal_skill(
    skill_id: UUID,
    permission: PermissionSource = Depends(get_permission_source),
    use_case: DeletePersonalSkillUseCase = Depends(get_delete_personal_skill_use_case),
) -> Response:
    """개인 스킬 삭제 — owner + DRAFT only. use case가 GCS SKILL.md → DB row 순으로 정리."""
    await use_case.execute(skill_id=skill_id, actor_user_id=permission.user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ── 마켓플레이스 browse (Team/Company 탭) ─────────────────────────────────────

# embedding(768d)·metadata·node_spec_staging(시스템 내부)는 응답에서 제외. node_definition_id는
# PUBLISHED 스킬이 NodeDefinition을 따라가는 데 필요해 포함. scope는 쿼리한 탭 구분용.
class MarketplaceSkillResponse(BaseModel):
    skill_id: UUID
    scope: SkillScope
    name: str
    description: str
    node_definition_id: UUID | None = None
    lifecycle_state: SkillState
    tags: list[str]
    version: str
    created_at: datetime
    updated_at: datetime


def _to_marketplace_response(
    skill: MarketplaceTeamSkill | MarketplaceCompanySkill, scope: SkillScope
) -> MarketplaceSkillResponse:
    return MarketplaceSkillResponse(
        skill_id=skill.skill_id,
        scope=scope,
        name=skill.name,
        description=skill.description,
        node_definition_id=skill.node_definition_id,
        lifecycle_state=SkillState(skill.lifecycle_state),
        tags=list(skill.tags),
        version=skill.version,
        created_at=skill.created_at,
        updated_at=skill.updated_at,
    )


@router.get("/marketplace", response_model=list[MarketplaceSkillResponse])
async def list_marketplace_skills(
    scope: SkillScope = Query(..., description="team | company (personal은 GET /personal 사용)"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    permission: PermissionSource = Depends(get_permission_source),
    use_case: ListMarketplaceSkillsUseCase = Depends(get_list_marketplace_skills_use_case),
) -> list[MarketplaceSkillResponse]:
    """마켓플레이스 Team/Company 탭 목록 — 검색어 없이 게시된 스킬을 최신순으로 나열.

    `SearchSkillsUseCase`(embedding 유사도, Composer 후보)와 별개의 browse 경로. company는
    전사 공개, team은 게시된 팀 스킬 전체(teams 테이블 부재로 팀별 필터는 후속). 인증된 사용자만 접근.

    `lifecycle_state`는 **PUBLISHED로 하드코딩**한다(Query 파라미터로 노출하지 않음). ADR-0020 (b):
    미검토 DRAFT/REVIEW를 마켓플레이스에 노출하지 않는다 — 클라가 `?lifecycle_state=draft`로
    미게시 스킬을 열람하는 것을 차단. 비-PUBLISHED 상태 조회는 관리/감사 경로(role 게이트)의 책임이며,
    port/use case의 `lifecycle_state` 인자는 그 내부 호출용으로 유지된다.

    scope=personal이면 use case→repo가 ValueError → 400으로 매핑(개인 목록은 GET /personal).
    """
    if scope == SkillScope.PERSONAL:
        raise HTTPException(
            status_code=400, detail="personal scope는 GET /api/v1/skills/personal을 사용하세요"
        )
    skills = await use_case.execute(
        scope=scope, lifecycle_state=SkillState.PUBLISHED, limit=limit, offset=offset
    )
    return [_to_marketplace_response(s, scope) for s in skills]


@router.get("/marketplace/{skill_id}", response_model=MarketplaceSkillResponse)
async def get_marketplace_skill(
    skill_id: UUID,
    scope: SkillScope = Query(..., description="team | company (personal은 GET /personal/{id} 사용)"),
    permission: PermissionSource = Depends(get_permission_source),
    use_case: GetMarketplaceSkillUseCase = Depends(get_get_marketplace_skill_use_case),
) -> MarketplaceSkillResponse:
    """마켓플레이스 스킬 단건 상세 — Team/Company 탭 카드 → 상세 페이지.

    목록과 동일하게 **PUBLISHED만** 반환(use case가 미게시/미존재를 동일 404로 가림 — id 직접
    접근으로 미검토 스킬 메타를 읽는 것 차단). 인증 필수. personal scope는 use case가
    `ValidationError`→400(개인 스킬은 GET /personal/{id}, owner 게이트).
    """
    skill = await use_case.execute(scope=scope, skill_id=skill_id)
    return _to_marketplace_response(skill, scope)


# instructions = SKILL.md markdown 본문(지침서). scripts/templates(선택 자산)는 상세 본문 노출엔
# 불필요해 제외 — 필요 시 별도 확장. embedding/메타는 단건 GET(위)에서 이미 제공.
class MarketplaceSkillDocumentResponse(BaseModel):
    skill_id: UUID
    name: str
    description: str
    instructions: str


@router.get("/marketplace/{skill_id}/document", response_model=MarketplaceSkillDocumentResponse)
async def get_marketplace_skill_document(
    skill_id: UUID,
    scope: SkillScope = Query(..., description="team | company"),
    permission: PermissionSource = Depends(get_permission_source),
    use_case: GetMarketplaceSkillDocumentUseCase = Depends(get_get_marketplace_skill_document_use_case),
) -> MarketplaceSkillDocumentResponse:
    """마켓플레이스 스킬 지침서(SKILL.md) 본문 — 상세 페이지가 메타 조회 후 lazy-load.

    단건 메타 조회와 동일하게 **PUBLISHED만**(use case가 미게시/미존재를 404로 가림). 지침서가
    GCS에 없으면(수동 생성 스킬 등) 404 → 프론트는 "등록된 지침서 없음"으로 graceful 처리.
    인증 필수. personal scope는 use case가 ValidationError→400.
    """
    document = await use_case.execute(scope=scope, skill_id=skill_id)
    return MarketplaceSkillDocumentResponse(
        skill_id=document.skill_id,
        name=document.name,
        description=document.description,
        instructions=document.instructions,
    )
