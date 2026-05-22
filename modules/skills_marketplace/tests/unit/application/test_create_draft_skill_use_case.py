from uuid import uuid4

import pytest
from common_schemas.enums import RiskLevel

from skills_marketplace.application.use_cases.create_draft_skill_use_case import CreateDraftSkillUseCase
from skills_marketplace.domain.value_objects.node_spec_staging import NodeSpecStaging
from skills_marketplace.domain.value_objects.skill_state import SkillState


class _Repo:
    def __init__(self):
        self.personal: dict = {}

    async def save_personal(self, skill):
        self.personal[skill.skill_id] = skill
        return skill


def _staging():
    return NodeSpecStaging(category="action", input_schema={}, output_schema={}, risk_level=RiskLevel.LOW)


@pytest.mark.asyncio
async def test_create_draft_personal_skill():
    # ADR-0020 ②e: Skills Builder(③)가 호출 — NodeDefinition 없이 MarketplaceSkill DRAFT 생성
    repo = _Repo()
    owner = uuid4()
    skill_id = await CreateDraftSkillUseCase(repo).execute(
        owner_user_id=owner,
        name="Slack 알림 스킬",
        description="슬랙으로 알림 전송",
        node_spec_staging=_staging(),
    )

    saved = repo.personal[skill_id]
    assert saved.owner_user_id == owner
    assert saved.name == "Slack 알림 스킬"
    assert saved.lifecycle_state == SkillState.DRAFT   # 검토 전 DRAFT
    assert saved.node_definition_id is None             # publish 전 NodeDefinition 미생성 (① 무관)
    assert saved.node_spec_staging.category == "action"  # 노드 스펙은 staging 보관


@pytest.mark.asyncio
async def test_create_draft_with_embedding_and_doc_uri():
    repo = _Repo()
    skill_id = await CreateDraftSkillUseCase(repo).execute(
        owner_user_id=uuid4(),
        name="요약 스킬",
        description="문서 요약",
        node_spec_staging=_staging(),
        embedding=[0.1] * 768,
        skill_document_uri="gs://bucket/skills/x/SKILL.md",
    )
    saved = repo.personal[skill_id]
    assert saved.embedding == [0.1] * 768
    assert saved.skill_document_uri == "gs://bucket/skills/x/SKILL.md"
