from datetime import UTC, datetime
from uuid import uuid4

import pytest
from common_schemas.enums import RiskLevel

from skills_marketplace.application.use_cases.publish_skill_use_case import PublishSkillUseCase
from skills_marketplace.domain.entities.marketplace_personal_skill import MarketplacePersonalSkill
from skills_marketplace.domain.entities.marketplace_team_skill import MarketplaceTeamSkill
from skills_marketplace.domain.value_objects import NodeSpecStaging, SkillScope, SkillState

_NOW = datetime.now(UTC)


class _SkillRepo:
    def __init__(self):
        self.personal: dict = {}
        self.team: dict = {}

    async def get_personal(self, sid):
        return self.personal.get(sid)

    async def get_team(self, sid):
        return self.team.get(sid)

    async def get_company(self, sid):
        return None

    async def save_personal(self, skill):
        self.personal[skill.skill_id] = skill
        return skill

    async def save_team(self, skill):
        self.team[skill.skill_id] = skill
        return skill

    async def save_company(self, skill):
        return skill


class _NodeDefRepo:
    def __init__(self):
        self.upserted: list = []

    async def upsert(self, node_def):
        self.upserted.append(node_def)
        return node_def


def _staging() -> NodeSpecStaging:
    return NodeSpecStaging(
        category="action",
        input_schema={"a": 1},
        output_schema={},
        risk_level=RiskLevel.HIGH,
        required_connections=["slack"],
        service_type="slack",
    )


# ADR-0020 Q1 + ②(d): publish(APPROVED→PUBLISHED) 시 staging → NodeDefinition 생성 (Option B)


@pytest.mark.asyncio
async def test_publish_personal_creates_node_definition():
    repo = _SkillRepo()
    node_def_repo = _NodeDefRepo()
    sid, owner = uuid4(), uuid4()
    repo.personal[sid] = MarketplacePersonalSkill(
        skill_id=sid, owner_user_id=owner, name="Slack 알림 스킬", description="슬랙 알림",
        node_spec_staging=_staging(), lifecycle_state=SkillState.APPROVED,
        embedding=[0.1] * 768, created_at=_NOW, updated_at=_NOW,
    )

    await PublishSkillUseCase(repo, node_def_repo).execute(sid, SkillScope.PERSONAL)

    # staging + skill 메타 → NodeDefinition 생성·upsert
    assert len(node_def_repo.upserted) == 1
    nd = node_def_repo.upserted[0]
    assert nd.name == "Slack 알림 스킬"
    assert nd.description == "슬랙 알림"
    assert nd.category == "action"
    assert nd.risk_level == RiskLevel.HIGH
    assert nd.required_connections == ["slack"]
    assert nd.service_type == "slack"
    assert nd.input_schema == {"a": 1}
    assert nd.embedding == [0.1] * 768
    assert nd.owner_user_id == owner   # personal scope → owner 격리
    assert nd.team_id is None

    # skill에 node_definition_id 연결 + PUBLISHED 전이
    updated = repo.personal[sid]
    assert updated.node_definition_id == nd.node_id
    assert updated.lifecycle_state == SkillState.PUBLISHED


@pytest.mark.asyncio
async def test_publish_team_scope_isolates_team_id():
    # ADR-0020 ① scope 격리: team 스킬 publish → NodeDefinition.team_id 채움, owner None
    repo = _SkillRepo()
    node_def_repo = _NodeDefRepo()
    sid, tid, author = uuid4(), uuid4(), uuid4()
    repo.team[sid] = MarketplaceTeamSkill(
        skill_id=sid, team_id=tid, author_id=author, name="팀 스킬", description="팀용",
        node_spec_staging=_staging(), lifecycle_state=SkillState.APPROVED,
        created_at=_NOW, updated_at=_NOW,
    )

    await PublishSkillUseCase(repo, node_def_repo).execute(sid, SkillScope.TEAM)

    nd = node_def_repo.upserted[0]
    assert nd.team_id == tid          # team scope → team_id 격리
    assert nd.owner_user_id is None   # owner 누출 없음
    assert repo.team[sid].node_definition_id == nd.node_id


@pytest.mark.asyncio
async def test_publish_skips_node_definition_when_already_linked():
    # node_definition_id가 이미 있으면(재게시 등) 중복 생성 안 함
    repo = _SkillRepo()
    node_def_repo = _NodeDefRepo()
    sid = uuid4()
    repo.personal[sid] = MarketplacePersonalSkill(
        skill_id=sid, owner_user_id=uuid4(), name="x", description="x",
        node_definition_id=uuid4(), lifecycle_state=SkillState.APPROVED,
        created_at=_NOW, updated_at=_NOW,
    )

    await PublishSkillUseCase(repo, node_def_repo).execute(sid, SkillScope.PERSONAL)

    assert len(node_def_repo.upserted) == 0
    assert repo.personal[sid].lifecycle_state == SkillState.PUBLISHED
