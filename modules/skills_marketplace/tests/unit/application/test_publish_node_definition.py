from datetime import UTC, datetime
from uuid import uuid4

import pytest
from common_schemas.enums import RiskLevel

from skills_marketplace.application.use_cases.publish_skill_use_case import PublishSkillUseCase
from skills_marketplace.domain.entities.marketplace_personal_skill import MarketplacePersonalSkill
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
    """ADR-0024 D2: 게시 시 NodeDef를 만들지 않으므로 upsert가 호출되지 않아야 한다."""

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


# ADR-0024 D2 (#372 결함 B): publish는 더 이상 NodeDefinition을 생성하지 않는다.
# 스킬은 "실행 노드"가 아니라 "LLM 노드 주입 지침서"(모델 A)이며 스킬 자체 임베딩으로 검색된다.
# (NodeDef를 만들면 일반 노드 검색에 섞여 워크플로우 노드로 둔갑 → 결함 B.)


@pytest.mark.asyncio
async def test_publish_does_not_create_node_definition():
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

    # D2: NodeDefinition 생성·upsert 안 함 + node_definition_id None 유지
    assert node_def_repo.upserted == []
    updated = repo.personal[sid]
    assert updated.node_definition_id is None
    assert updated.lifecycle_state == SkillState.PUBLISHED


@pytest.mark.asyncio
async def test_publish_succeeds_without_node_def_repo():
    # node_def_repo 미주입(Optional, ADR-0024 D2)이어도 게시 성공 — 더 이상 필요 없음.
    repo = _SkillRepo()
    sid, owner = uuid4(), uuid4()
    repo.personal[sid] = MarketplacePersonalSkill(
        skill_id=sid, owner_user_id=owner, name="x", description="x",
        node_spec_staging=_staging(), lifecycle_state=SkillState.APPROVED,
        embedding=[0.1] * 768, created_at=_NOW, updated_at=_NOW,
    )

    await PublishSkillUseCase(repo).execute(
        sid, SkillScope.PERSONAL, actor_user_id=owner, actor_role="User"
    )

    assert repo.personal[sid].lifecycle_state == SkillState.PUBLISHED
    assert repo.personal[sid].node_definition_id is None


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


# --- 검색용 임베딩 백필 (D2 후에도 스킬 자체 검색을 위해 유지) ---


@pytest.mark.asyncio
async def test_publish_backfills_embedding_when_missing():
    # embedding=None 스킬도 publish 시 embedder로 백필 → skill row가 채워져 스킬 검색에 노출.
    repo, embedder = _SkillRepo(), _Embedder(vec=[0.7] * 768)
    sid, owner = uuid4(), uuid4()
    repo.personal[sid] = _personal_skill(sid, owner, embedding=None)

    await PublishSkillUseCase(repo, embedder=embedder).execute(
        sid, SkillScope.PERSONAL, actor_user_id=owner, actor_role="User"
    )

    assert embedder.calls == ["문서를 요약하는 스킬"]      # description으로 임베딩
    assert repo.personal[sid].embedding == [0.7] * 768      # skill row 백필


@pytest.mark.asyncio
async def test_publish_keeps_existing_embedding_no_embed_call():
    # 이미 임베딩 있으면 embedder 호출 안 함(불필요 Modal 호출/비용 회피).
    repo, embedder = _SkillRepo(), _Embedder()
    sid, owner = uuid4(), uuid4()
    repo.personal[sid] = _personal_skill(sid, owner, embedding=[0.1] * 768)

    await PublishSkillUseCase(repo, embedder=embedder).execute(
        sid, SkillScope.PERSONAL, actor_user_id=owner, actor_role="User"
    )

    assert embedder.calls == []


@pytest.mark.asyncio
async def test_publish_without_embedder_leaves_none():
    # embedder 미주입(하위호환) — 임베딩 None이어도 publish는 성공(검색만 누락).
    repo = _SkillRepo()
    sid, owner = uuid4(), uuid4()
    repo.personal[sid] = _personal_skill(sid, owner, embedding=None)

    await PublishSkillUseCase(repo).execute(
        sid, SkillScope.PERSONAL, actor_user_id=owner, actor_role="User"
    )

    assert repo.personal[sid].lifecycle_state == SkillState.PUBLISHED
    assert repo.personal[sid].embedding is None


@pytest.mark.asyncio
async def test_publish_embedding_failure_is_non_fatal():
    # embedder 실패해도 게시는 진행(검색 누락은 감수, 게시 차단 안 함).
    repo, embedder = _SkillRepo(), _Embedder(fail=True)
    sid, owner = uuid4(), uuid4()
    repo.personal[sid] = _personal_skill(sid, owner, embedding=None)

    await PublishSkillUseCase(repo, embedder=embedder).execute(
        sid, SkillScope.PERSONAL, actor_user_id=owner, actor_role="User"
    )

    assert repo.personal[sid].lifecycle_state == SkillState.PUBLISHED
    assert repo.personal[sid].embedding is None
