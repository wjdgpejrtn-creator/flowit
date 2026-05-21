from datetime import UTC, datetime
from uuid import uuid4

from common_schemas.enums import RiskLevel

from skills_marketplace.domain.entities.marketplace_company_skill import MarketplaceCompanySkill
from skills_marketplace.domain.entities.marketplace_personal_skill import MarketplacePersonalSkill
from skills_marketplace.domain.entities.marketplace_team_skill import MarketplaceTeamSkill
from skills_marketplace.domain.value_objects.node_spec_staging import NodeSpecStaging
from skills_marketplace.domain.value_objects.skill_state import SkillState

_NOW = datetime.now(UTC)


def _staging() -> NodeSpecStaging:
    return NodeSpecStaging(category="action", input_schema={}, output_schema={}, risk_level=RiskLevel.LOW)


# ADR-0020 Q1: DRAFT 시점엔 NodeDefinition 미생성 → node_definition_id=None + 노드 스펙은 staging 보관


def test_personal_node_def_optional_and_staging():
    skill = MarketplacePersonalSkill(
        skill_id=uuid4(), owner_user_id=uuid4(), name="T", description="x",
        node_spec_staging=_staging(), created_at=_NOW, updated_at=_NOW,
    )
    assert skill.node_definition_id is None
    assert skill.node_spec_staging.category == "action"
    assert skill.lifecycle_state == SkillState.DRAFT


def test_personal_published_with_node_def():
    nid = uuid4()
    skill = MarketplacePersonalSkill(
        skill_id=uuid4(), owner_user_id=uuid4(), name="T", description="x",
        node_definition_id=nid, lifecycle_state=SkillState.PUBLISHED, created_at=_NOW, updated_at=_NOW,
    )
    assert skill.node_definition_id == nid


def test_team_node_def_optional_and_staging():
    skill = MarketplaceTeamSkill(
        skill_id=uuid4(), team_id=uuid4(), author_id=uuid4(), name="T", description="x",
        node_spec_staging=_staging(), created_at=_NOW, updated_at=_NOW,
    )
    assert skill.node_definition_id is None
    assert skill.node_spec_staging.required_connections == []


def test_company_node_def_optional_and_staging():
    skill = MarketplaceCompanySkill(
        skill_id=uuid4(), author_id=uuid4(), name="T", description="x",
        node_spec_staging=_staging(), created_at=_NOW, updated_at=_NOW,
    )
    assert skill.node_definition_id is None
