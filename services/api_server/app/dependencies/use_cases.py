from __future__ import annotations

import os

from fastapi import Depends
from nodes_graph.application.use_cases.validate_graph_use_case import ValidateGraphUseCase
from nodes_graph.domain.ports.node_definition_repository import NodeDefinitionRepository
from nodes_graph.domain.services.graph_validator import GraphValidator
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
from skills_marketplace.domain.ports.skill_document_store import SkillDocumentStore
from skills_marketplace.domain.ports.skill_repository import SkillRepository

from app.dependencies.repositories import (
    get_marketplace_skill_repository,
    get_node_definition_repository,
)
from app.dependencies.storage import get_skill_document_store


def get_graph_validator(
    node_def_repo: NodeDefinitionRepository = Depends(get_node_definition_repository),
) -> GraphValidator:
    return GraphValidator(node_def_repo=node_def_repo)


def get_validate_graph_use_case(
    validator: GraphValidator = Depends(get_graph_validator),
) -> ValidateGraphUseCase:
    return ValidateGraphUseCase(validator=validator)


def get_submit_skill_use_case(
    repo: SkillRepository = Depends(get_marketplace_skill_repository),
) -> SubmitSkillUseCase:
    return SubmitSkillUseCase(repo=repo)


def get_list_review_queue_use_case(
    repo: SkillRepository = Depends(get_marketplace_skill_repository),
) -> ListReviewQueueUseCase:
    return ListReviewQueueUseCase(repo=repo)


def get_promote_to_team_use_case(
    repo: SkillRepository = Depends(get_marketplace_skill_repository),
) -> PromoteToTeamUseCase:
    """personal → team 승격 (재심사 리셋: 새 team 스킬 DRAFT 생성). 박아름 use case 재사용."""
    return PromoteToTeamUseCase(repo=repo)


def get_promote_to_company_use_case(
    repo: SkillRepository = Depends(get_marketplace_skill_repository),
) -> PromoteToCompanyUseCase:
    """team → company 승격 (재심사 리셋: 새 company 스킬 DRAFT 생성). 박아름 use case 재사용."""
    return PromoteToCompanyUseCase(repo=repo)


def get_approve_skill_use_case(
    repo: SkillRepository = Depends(get_marketplace_skill_repository),
) -> ApproveSkillUseCase:
    return ApproveSkillUseCase(repo=repo)


def get_publish_skill_use_case(
    repo: SkillRepository = Depends(get_marketplace_skill_repository),
    node_def_repo: NodeDefinitionRepository = Depends(get_node_definition_repository),
) -> PublishSkillUseCase:
    # EMBEDDING_BASE_URL 설정 시에만 embedder 주입 — 게시 시 임베딩 누락 스킬을 백필해
    # Composer 검색/NodeDefinition 카탈로그에 노출(미설정이면 None → 기존 동작 유지, 하위호환).
    embedder = None
    if os.getenv("EMBEDDING_BASE_URL"):
        from ai_agent.adapters.llm.modal_embedding_adapter import ModalEmbeddingAdapter

        embedder = ModalEmbeddingAdapter()
    return PublishSkillUseCase(repo=repo, node_def_repo=node_def_repo, embedder=embedder)


# ── personal skills CRUD (REQ-013, 가원 요청) ─────────────────────────────────


def get_create_draft_skill_use_case(
    repo: SkillRepository = Depends(get_marketplace_skill_repository),
    doc_store: SkillDocumentStore = Depends(get_skill_document_store),
) -> CreateDraftSkillUseCase:
    """스킬빌더 폼 → 개인 DRAFT 생성 (REQ-010). doc_store는 ADR-0017 SKILL.md 이중 저장용."""
    return CreateDraftSkillUseCase(repo=repo, doc_store=doc_store)


def get_list_personal_skills_use_case(
    repo: SkillRepository = Depends(get_marketplace_skill_repository),
) -> ListUserPersonalSkillsUseCase:
    return ListUserPersonalSkillsUseCase(repo=repo)


def get_list_marketplace_skills_use_case(
    repo: SkillRepository = Depends(get_marketplace_skill_repository),
) -> ListMarketplaceSkillsUseCase:
    """마켓플레이스 Team/Company 탭 browse 목록 (검색어 없는 게시 스킬 나열)."""
    return ListMarketplaceSkillsUseCase(repo=repo)


def get_get_marketplace_skill_use_case(
    repo: SkillRepository = Depends(get_marketplace_skill_repository),
) -> GetMarketplaceSkillUseCase:
    """마켓플레이스(team/company) 스킬 단건 조회 — browse 상세 페이지 (PUBLISHED만)."""
    return GetMarketplaceSkillUseCase(repo=repo)


def get_get_marketplace_skill_document_use_case(
    repo: SkillRepository = Depends(get_marketplace_skill_repository),
    doc_store: SkillDocumentStore = Depends(get_skill_document_store),
) -> GetMarketplaceSkillDocumentUseCase:
    """마켓플레이스 스킬 지침서(SKILL.md) 조회 — 상세 페이지 본문 (PUBLISHED만, GCS load)."""
    return GetMarketplaceSkillDocumentUseCase(repo=repo, doc_store=doc_store)


def get_get_personal_skill_use_case(
    repo: SkillRepository = Depends(get_marketplace_skill_repository),
) -> GetPersonalSkillUseCase:
    return GetPersonalSkillUseCase(repo=repo)


def get_get_personal_skill_document_use_case(
    repo: SkillRepository = Depends(get_marketplace_skill_repository),
    doc_store: SkillDocumentStore = Depends(get_skill_document_store),
) -> GetPersonalSkillDocumentUseCase:
    """개인 스킬 지침서(SKILL.md) 조회 — 상세 페이지 본문 (owner only, 상태 무관, GCS load)."""
    return GetPersonalSkillDocumentUseCase(repo=repo, doc_store=doc_store)


def get_update_personal_skill_use_case(
    repo: SkillRepository = Depends(get_marketplace_skill_repository),
    doc_store: SkillDocumentStore = Depends(get_skill_document_store),
) -> UpdatePersonalSkillUseCase:
    """개인 스킬 수정 — doc_store는 instructions(SKILL.md) 본문 재저장용(ADR-0017)."""
    return UpdatePersonalSkillUseCase(repo=repo, doc_store=doc_store)


def get_delete_personal_skill_use_case(
    repo: SkillRepository = Depends(get_marketplace_skill_repository),
    doc_store: SkillDocumentStore = Depends(get_skill_document_store),
) -> DeletePersonalSkillUseCase:
    return DeletePersonalSkillUseCase(repo=repo, doc_store=doc_store)
