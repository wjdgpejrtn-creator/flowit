"""Marketplace 3계층 Skill Mapper 왕복 변환 단위 테스트 (ADR-0020 ②).

NodeSpecStaging VO ↔ staging_* 평탄 컬럼 변환이 핵심 검증 대상.
created_at/updated_at은 DB server_default 관리라 to_orm이 싣지 않으므로,
왕복 테스트는 to_orm 결과에 타임스탬프를 주입(=DB write 시뮬레이션) 후 to_domain한다.
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from common_schemas.enums import RiskLevel
from skills_marketplace.domain.entities.approval_workflow import ApprovalWorkflow
from skills_marketplace.domain.entities.marketplace_company_skill import MarketplaceCompanySkill
from skills_marketplace.domain.entities.marketplace_personal_skill import MarketplacePersonalSkill
from skills_marketplace.domain.entities.marketplace_team_skill import MarketplaceTeamSkill
from skills_marketplace.domain.value_objects.node_spec_staging import NodeSpecStaging
from skills_marketplace.domain.value_objects.skill_scope import SkillScope

from storage.mappers.marketplace_skill_mapper import (
    CompanySkillMapper,
    PersonalSkillMapper,
    SkillApprovalMapper,
    TeamSkillMapper,
)

_NOW = datetime(2026, 5, 22, 12, 0, 0, tzinfo=timezone.utc)


def _staging() -> NodeSpecStaging:
    return NodeSpecStaging(
        category="communication",
        input_schema={"type": "object"},
        output_schema={"type": "object"},
        risk_level=RiskLevel.MEDIUM,
        required_connections=["slack"],
        service_type="slack",
    )


def _roundtrip_orm(mapper, entity):
    """to_orm → (DB 타임스탬프 시뮬레이션) → to_domain."""
    orm = mapper.to_orm(entity)
    orm.created_at = entity.created_at
    orm.updated_at = entity.updated_at
    return mapper.to_domain(orm)


class TestPersonalSkillMapper:
    def test_roundtrip_with_staging(self):
        entity = MarketplacePersonalSkill(
            skill_id=uuid4(),
            owner_user_id=uuid4(),
            name="슬랙 알림 스킬",
            description="슬랙으로 알림",
            node_spec_staging=_staging(),
            embedding=[0.1, 0.2, 0.3],
            tags=["notify"],
            metadata={"src": "sop"},
            created_at=_NOW,
            updated_at=_NOW,
        )
        assert _roundtrip_orm(PersonalSkillMapper, entity) == entity

    def test_roundtrip_no_staging_published(self):
        entity = MarketplacePersonalSkill(
            skill_id=uuid4(),
            owner_user_id=uuid4(),
            name="x",
            description="y",
            node_definition_id=uuid4(),
            node_spec_staging=None,
            created_at=_NOW,
            updated_at=_NOW,
        )
        result = _roundtrip_orm(PersonalSkillMapper, entity)
        assert result == entity
        assert result.node_spec_staging is None

    def test_to_orm_flattens_staging(self):
        entity = MarketplacePersonalSkill(
            skill_id=uuid4(), owner_user_id=uuid4(), name="x", description="y",
            node_spec_staging=_staging(), created_at=_NOW, updated_at=_NOW,
        )
        orm = PersonalSkillMapper.to_orm(entity)
        assert orm.staging_category == "communication"
        assert orm.staging_risk_level == "Medium"
        assert orm.staging_required_connections == ["slack"]
        assert orm.skill_metadata == {}  # entity.metadata 기본값


class TestTeamSkillMapper:
    def test_roundtrip(self):
        entity = MarketplaceTeamSkill(
            skill_id=uuid4(),
            team_id=uuid4(),
            author_id=uuid4(),
            name="팀 스킬",
            description="설명",
            node_spec_staging=_staging(),
            promoted_from=uuid4(),
            created_at=_NOW,
            updated_at=_NOW,
        )
        assert _roundtrip_orm(TeamSkillMapper, entity) == entity


class TestCompanySkillMapper:
    def test_roundtrip(self):
        entity = MarketplaceCompanySkill(
            skill_id=uuid4(),
            author_id=uuid4(),
            name="전사 스킬",
            description="설명",
            node_definition_id=uuid4(),
            node_spec_staging=None,
            created_at=_NOW,
            updated_at=_NOW,
        )
        assert _roundtrip_orm(CompanySkillMapper, entity) == entity


class TestSkillApprovalMapper:
    """ApprovalWorkflow ↔ skill_approvals. created_at은 엔티티가 들고 있어 to_orm이
    그대로 싣는다 → 타임스탬프 재주입 없이 직접 왕복."""

    def test_roundtrip_approved(self):
        approval = ApprovalWorkflow(
            approval_id=uuid4(),
            skill_id=uuid4(),
            scope=SkillScope.TEAM,
            reviewer_id=uuid4(),
            status="approved",
            comment="LGTM",
            reviewed_at=_NOW,
            created_at=_NOW,
        )
        result = SkillApprovalMapper.to_domain(SkillApprovalMapper.to_orm(approval))
        assert result == approval

    def test_roundtrip_pending_no_review(self):
        approval = ApprovalWorkflow(
            approval_id=uuid4(),
            skill_id=uuid4(),
            scope=SkillScope.PERSONAL,
            reviewer_id=uuid4(),
            status="pending",
            created_at=_NOW,
        )
        result = SkillApprovalMapper.to_domain(SkillApprovalMapper.to_orm(approval))
        assert result == approval
        assert result.scope == SkillScope.PERSONAL
        assert result.reviewed_at is None
