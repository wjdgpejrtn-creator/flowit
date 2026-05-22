from __future__ import annotations

from typing import Any

from common_schemas.enums import RiskLevel
from skills_marketplace.domain.entities.approval_workflow import ApprovalWorkflow
from skills_marketplace.domain.entities.marketplace_company_skill import MarketplaceCompanySkill
from skills_marketplace.domain.entities.marketplace_personal_skill import MarketplacePersonalSkill
from skills_marketplace.domain.entities.marketplace_team_skill import MarketplaceTeamSkill
from skills_marketplace.domain.value_objects.node_spec_staging import NodeSpecStaging
from skills_marketplace.domain.value_objects.skill_scope import SkillScope

from ..orm.marketplace_skill_model import (
    CompanySkillModel,
    PersonalSkillModel,
    SkillApprovalModel,
    TeamSkillModel,
)

# ADR-0020 Q1: NodeSpecStaging VO ↔ staging_* 평탄 컬럼. category가 NodeSpecStaging의
# 필수 필드라, staging_category 존재 여부로 staging 유무를 판별한다.


def _staging_to_domain(orm: Any) -> NodeSpecStaging | None:
    if orm.staging_category is None:
        return None
    return NodeSpecStaging(
        category=orm.staging_category,
        input_schema=orm.staging_input_schema or {},
        output_schema=orm.staging_output_schema or {},
        risk_level=RiskLevel(orm.staging_risk_level),
        required_connections=list(orm.staging_required_connections or []),
        service_type=orm.staging_service_type,
    )


def _staging_to_orm_kwargs(staging: NodeSpecStaging | None) -> dict[str, Any]:
    if staging is None:
        return {
            "staging_category": None,
            "staging_input_schema": None,
            "staging_output_schema": None,
            "staging_risk_level": None,
            "staging_required_connections": None,
            "staging_service_type": None,
        }
    return {
        "staging_category": staging.category,
        "staging_input_schema": staging.input_schema,
        "staging_output_schema": staging.output_schema,
        "staging_risk_level": staging.risk_level.value,
        "staging_required_connections": list(staging.required_connections),
        "staging_service_type": staging.service_type,
    }


def _common_to_domain_kwargs(orm: Any) -> dict[str, Any]:
    """3계층 공통 도메인 필드 — 각 Mapper가 scope별 필드를 더해 엔티티를 생성한다."""
    return {
        "skill_id": orm.skill_id,
        "name": orm.name,
        "description": orm.description,
        "node_definition_id": orm.node_definition_id,
        "node_spec_staging": _staging_to_domain(orm),
        "lifecycle_state": orm.lifecycle_state,  # str → SkillState (pydantic 강제)
        "skill_document_uri": orm.skill_document_uri,
        "embedding": list(orm.embedding) if orm.embedding is not None else None,
        "workflow_id": orm.workflow_id,
        "tags": list(orm.tags),
        "version": orm.version,
        "metadata": dict(orm.skill_metadata),
        "created_at": orm.created_at,
        "updated_at": orm.updated_at,
    }


def _common_to_orm_kwargs(entity: Any) -> dict[str, Any]:
    """3계층 공통 ORM 컬럼 kwargs (staging 평탄화 포함)."""
    return {
        "skill_id": entity.skill_id,
        "name": entity.name,
        "description": entity.description,
        "node_definition_id": entity.node_definition_id,
        "lifecycle_state": entity.lifecycle_state.value,
        "skill_document_uri": entity.skill_document_uri,
        "embedding": entity.embedding,
        "workflow_id": entity.workflow_id,
        "tags": list(entity.tags),
        "version": entity.version,
        "skill_metadata": dict(entity.metadata),
        **_staging_to_orm_kwargs(entity.node_spec_staging),
    }


class PersonalSkillMapper:
    @staticmethod
    def to_domain(orm: PersonalSkillModel) -> MarketplacePersonalSkill:
        return MarketplacePersonalSkill(
            **_common_to_domain_kwargs(orm),
            owner_user_id=orm.owner_user_id,
            promoted_to_team_id=orm.promoted_to_team_id,
        )

    @staticmethod
    def to_orm(entity: MarketplacePersonalSkill) -> PersonalSkillModel:
        return PersonalSkillModel(
            **_common_to_orm_kwargs(entity),
            owner_user_id=entity.owner_user_id,
            promoted_to_team_id=entity.promoted_to_team_id,
        )


class TeamSkillMapper:
    @staticmethod
    def to_domain(orm: TeamSkillModel) -> MarketplaceTeamSkill:
        return MarketplaceTeamSkill(
            **_common_to_domain_kwargs(orm),
            team_id=orm.team_id,
            author_id=orm.author_id,
            promoted_from=orm.promoted_from,
            promoted_to_company_id=orm.promoted_to_company_id,
        )

    @staticmethod
    def to_orm(entity: MarketplaceTeamSkill) -> TeamSkillModel:
        return TeamSkillModel(
            **_common_to_orm_kwargs(entity),
            team_id=entity.team_id,
            author_id=entity.author_id,
            promoted_from=entity.promoted_from,
            promoted_to_company_id=entity.promoted_to_company_id,
        )


class CompanySkillMapper:
    @staticmethod
    def to_domain(orm: CompanySkillModel) -> MarketplaceCompanySkill:
        return MarketplaceCompanySkill(
            **_common_to_domain_kwargs(orm),
            author_id=orm.author_id,
            promoted_from=orm.promoted_from,
        )

    @staticmethod
    def to_orm(entity: MarketplaceCompanySkill) -> CompanySkillModel:
        return CompanySkillModel(
            **_common_to_orm_kwargs(entity),
            author_id=entity.author_id,
            promoted_from=entity.promoted_from,
        )


class SkillApprovalMapper:
    """`ApprovalWorkflow` ↔ `skill_approvals`.

    `ApprovalWorkflow.scope`(`SkillScope`)는 skill_approvals의 polymorphic `skill_id`가
    어느 3계층 테이블 소속인지 구분한다 (PR #146, 조장 A안).
    """

    @staticmethod
    def to_domain(orm: SkillApprovalModel) -> ApprovalWorkflow:
        return ApprovalWorkflow(
            approval_id=orm.approval_id,
            skill_id=orm.skill_id,
            scope=SkillScope(orm.scope),
            reviewer_id=orm.reviewer_id,
            status=orm.status,  # str → Literal
            comment=orm.comment,
            reviewed_at=orm.reviewed_at,
            created_at=orm.created_at,
        )

    @staticmethod
    def to_orm(approval: ApprovalWorkflow) -> SkillApprovalModel:
        return SkillApprovalModel(
            approval_id=approval.approval_id,
            skill_id=approval.skill_id,
            scope=approval.scope.value,
            reviewer_id=approval.reviewer_id,
            status=approval.status,
            comment=approval.comment,
            reviewed_at=approval.reviewed_at,
            created_at=approval.created_at,
        )
