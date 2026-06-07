"""게시 시 온톨로지 BINDS 투영 훅 (ADR-0026 Phase 2b).

publish가 SkillOntologyProjector를 비치명적으로 호출하는지 검증. Neo4j/실제 어댑터 없이
가짜 projector로 호출 인자를 캡처한다.
"""
from __future__ import annotations

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

    async def get_personal(self, sid):
        return self.personal.get(sid)

    async def get_team(self, sid):
        return None

    async def get_company(self, sid):
        return None

    async def save_personal(self, skill):
        self.personal[skill.skill_id] = skill
        return skill

    async def save_team(self, skill):
        return skill

    async def save_company(self, skill):
        return skill


class _Projector:
    def __init__(self, fail=False):
        self.calls: list = []
        self._fail = fail

    async def project_skill(self, *, skill_id, scope, required_connections=()):
        self.calls.append((skill_id, scope, list(required_connections)))
        if self._fail:
            raise RuntimeError("neo4j down")


def _staging() -> NodeSpecStaging:
    return NodeSpecStaging(
        category="action",
        input_schema={},
        output_schema={},
        risk_level=RiskLevel.HIGH,
        required_connections=["slack", "slack", ""],  # dedup/falsy는 어댑터 책임이지만 그대로 전달
        service_type="slack",
    )


def _skill(sid, owner, *, staging=None):
    return MarketplacePersonalSkill(
        skill_id=sid, owner_user_id=owner, name="Slack 스킬", description="슬랙 알림",
        node_spec_staging=staging, lifecycle_state=SkillState.APPROVED,
        embedding=[0.1] * 768, created_at=_NOW, updated_at=_NOW,
    )


@pytest.mark.asyncio
async def test_publish_projects_skill_with_required_connections():
    repo, projector = _SkillRepo(), _Projector()
    sid, owner = uuid4(), uuid4()
    repo.personal[sid] = _skill(sid, owner, staging=_staging())

    await PublishSkillUseCase(repo, ontology_projector=projector).execute(
        sid, SkillScope.PERSONAL, actor_user_id=owner, actor_role="User"
    )

    assert len(projector.calls) == 1
    called_id, called_scope, called_conns = projector.calls[0]
    assert called_id == sid
    assert called_scope == SkillScope.PERSONAL
    # staging.required_connections 그대로 전달 (정규화는 어댑터/projector 책임)
    assert called_conns == ["slack", "slack", ""]
    assert repo.personal[sid].lifecycle_state == SkillState.PUBLISHED


@pytest.mark.asyncio
async def test_publish_projects_with_empty_connections_when_no_staging():
    repo, projector = _SkillRepo(), _Projector()
    sid, owner = uuid4(), uuid4()
    repo.personal[sid] = _skill(sid, owner, staging=None)

    await PublishSkillUseCase(repo, ontology_projector=projector).execute(
        sid, SkillScope.PERSONAL, actor_user_id=owner, actor_role="User"
    )

    assert projector.calls[0][2] == []  # staging 없으면 connection 없음 (ai 노드 BINDS만)


@pytest.mark.asyncio
async def test_publish_succeeds_when_projector_missing():
    # projector 미주입(하위호환) — 게시 성공.
    repo = _SkillRepo()
    sid, owner = uuid4(), uuid4()
    repo.personal[sid] = _skill(sid, owner, staging=_staging())

    await PublishSkillUseCase(repo).execute(
        sid, SkillScope.PERSONAL, actor_user_id=owner, actor_role="User"
    )

    assert repo.personal[sid].lifecycle_state == SkillState.PUBLISHED


@pytest.mark.asyncio
async def test_publish_ontology_failure_is_non_fatal():
    # projector가 던져도 게시는 유지(검색 누락 감수, 게시 차단 안 함).
    repo, projector = _SkillRepo(), _Projector(fail=True)
    sid, owner = uuid4(), uuid4()
    repo.personal[sid] = _skill(sid, owner, staging=_staging())

    await PublishSkillUseCase(repo, ontology_projector=projector).execute(
        sid, SkillScope.PERSONAL, actor_user_id=owner, actor_role="User"
    )

    assert repo.personal[sid].lifecycle_state == SkillState.PUBLISHED
    assert len(projector.calls) == 1  # 호출은 됐고 실패만 삼켰다
