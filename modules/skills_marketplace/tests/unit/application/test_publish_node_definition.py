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
# (위임2 인가: personal=owner / team=team_manager+dept 로 actor 전달)


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

    await PublishSkillUseCase(repo, node_def_repo).execute(
        sid, SkillScope.PERSONAL, actor_user_id=owner, actor_role="User"
    )

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

    # team publish 인가: 같은 부서(team_id) team_manager
    await PublishSkillUseCase(repo, node_def_repo).execute(
        sid, SkillScope.TEAM, actor_user_id=uuid4(), actor_role="team_manager", actor_department_id=tid
    )

    nd = node_def_repo.upserted[0]
    assert nd.team_id == tid          # team scope → team_id 격리
    assert nd.owner_user_id is None   # owner 누출 없음
    assert repo.team[sid].node_definition_id == nd.node_id


class _Embedder:
    """embed 호출을 기록하는 가짜 EmbedderPort."""

    def __init__(self, vec=None, fail=False):
        self.calls: list = []
        self._vec = vec if vec is not None else [0.7] * 768
        self._fail = fail

    async def embed(self, text):
        self.calls.append(text)
        if self._fail:
            raise RuntimeError("embed service down")
        return self._vec


def _personal_skill(sid, owner, embedding):
    return MarketplacePersonalSkill(
        skill_id=sid, owner_user_id=owner, name="AI 문서 요약", description="문서를 요약하는 스킬",
        node_spec_staging=_staging(), lifecycle_state=SkillState.APPROVED,
        embedding=embedding, created_at=_NOW, updated_at=_NOW,
    )


@pytest.mark.asyncio
async def test_publish_backfills_embedding_when_missing():
    # 생성 경로가 임베딩을 안 채운 스킬(embedding=None)도 publish 시 embedder로 백필 →
    # skill row + NodeDefinition 둘 다 임베딩이 채워져 검색에 노출.
    repo, node_def_repo, embedder = _SkillRepo(), _NodeDefRepo(), _Embedder(vec=[0.7] * 768)
    sid, owner = uuid4(), uuid4()
    repo.personal[sid] = _personal_skill(sid, owner, embedding=None)

    await PublishSkillUseCase(repo, node_def_repo, embedder=embedder).execute(
        sid, SkillScope.PERSONAL, actor_user_id=owner, actor_role="User"
    )

    assert embedder.calls == ["문서를 요약하는 스킬"]          # description으로 임베딩
    assert repo.personal[sid].embedding == [0.7] * 768          # skill row 백필
    assert node_def_repo.upserted[0].embedding == [0.7] * 768   # NodeDefinition도 백필


@pytest.mark.asyncio
async def test_publish_keeps_existing_embedding_no_embed_call():
    # 이미 임베딩 있으면 embedder 호출 안 함(불필요 Modal 호출/비용 회피).
    repo, node_def_repo, embedder = _SkillRepo(), _NodeDefRepo(), _Embedder()
    sid, owner = uuid4(), uuid4()
    repo.personal[sid] = _personal_skill(sid, owner, embedding=[0.1] * 768)

    await PublishSkillUseCase(repo, node_def_repo, embedder=embedder).execute(
        sid, SkillScope.PERSONAL, actor_user_id=owner, actor_role="User"
    )

    assert embedder.calls == []
    assert node_def_repo.upserted[0].embedding == [0.1] * 768


@pytest.mark.asyncio
async def test_publish_without_embedder_leaves_none():
    # embedder 미주입(하위호환) — 임베딩 None이어도 publish는 성공(검색만 누락).
    repo, node_def_repo = _SkillRepo(), _NodeDefRepo()
    sid, owner = uuid4(), uuid4()
    repo.personal[sid] = _personal_skill(sid, owner, embedding=None)

    await PublishSkillUseCase(repo, node_def_repo).execute(
        sid, SkillScope.PERSONAL, actor_user_id=owner, actor_role="User"
    )

    assert repo.personal[sid].lifecycle_state == SkillState.PUBLISHED
    assert repo.personal[sid].embedding is None
    assert node_def_repo.upserted[0].embedding is None


@pytest.mark.asyncio
async def test_publish_embedding_failure_is_non_fatal():
    # embedder 실패해도 게시는 진행(검색 누락은 감수, 게시 차단 안 함).
    repo, node_def_repo, embedder = _SkillRepo(), _NodeDefRepo(), _Embedder(fail=True)
    sid, owner = uuid4(), uuid4()
    repo.personal[sid] = _personal_skill(sid, owner, embedding=None)

    await PublishSkillUseCase(repo, node_def_repo, embedder=embedder).execute(
        sid, SkillScope.PERSONAL, actor_user_id=owner, actor_role="User"
    )

    assert repo.personal[sid].lifecycle_state == SkillState.PUBLISHED
    assert repo.personal[sid].embedding is None


@pytest.mark.asyncio
async def test_publish_skips_node_definition_when_already_linked():
    # node_definition_id가 이미 있으면(재게시 등) 중복 생성 안 함
    repo = _SkillRepo()
    node_def_repo = _NodeDefRepo()
    sid, owner = uuid4(), uuid4()
    repo.personal[sid] = MarketplacePersonalSkill(
        skill_id=sid, owner_user_id=owner, name="x", description="x",
        node_definition_id=uuid4(), lifecycle_state=SkillState.APPROVED,
        created_at=_NOW, updated_at=_NOW,
    )

    await PublishSkillUseCase(repo, node_def_repo).execute(
        sid, SkillScope.PERSONAL, actor_user_id=owner, actor_role="User"
    )

    assert len(node_def_repo.upserted) == 0
    assert repo.personal[sid].lifecycle_state == SkillState.PUBLISHED
