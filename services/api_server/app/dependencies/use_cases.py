from __future__ import annotations

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
    GetPersonalSkillUseCase,
    ListMarketplaceSkillsUseCase,
    ListReviewQueueUseCase,
    ListUserPersonalSkillsUseCase,
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


def get_approve_skill_use_case(
    repo: SkillRepository = Depends(get_marketplace_skill_repository),
) -> ApproveSkillUseCase:
    return ApproveSkillUseCase(repo=repo)


def get_publish_skill_use_case(
    repo: SkillRepository = Depends(get_marketplace_skill_repository),
    node_def_repo: NodeDefinitionRepository = Depends(get_node_definition_repository),
) -> PublishSkillUseCase:
    return PublishSkillUseCase(repo=repo, node_def_repo=node_def_repo)


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


def get_update_personal_skill_use_case(
    repo: SkillRepository = Depends(get_marketplace_skill_repository),
) -> UpdatePersonalSkillUseCase:
    return UpdatePersonalSkillUseCase(repo=repo)


def get_delete_personal_skill_use_case(
    repo: SkillRepository = Depends(get_marketplace_skill_repository),
    doc_store: SkillDocumentStore = Depends(get_skill_document_store),
) -> DeletePersonalSkillUseCase:
    return DeletePersonalSkillUseCase(repo=repo, doc_store=doc_store)
