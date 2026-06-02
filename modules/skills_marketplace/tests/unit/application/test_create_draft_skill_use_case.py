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


class _DocStore:
    """In-memory SkillDocumentStore — save가 gs:// URI 반환 (어댑터 계약 모사)."""

    def __init__(self):
        self.saved: dict = {}

    async def save(self, skill_id, document) -> str:
        self.saved[skill_id] = document
        return f"gs://test-bucket/skills/{skill_id}/SKILL.md"

    async def load(self, skill_id):
        return self.saved.get(skill_id)


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


@pytest.mark.asyncio
async def test_create_draft_saves_skill_document_and_sets_returned_uri():
    # ADR-0017 이중 저장: doc_store + instructions → SkillDocument GCS 저장 + 반환 URI를 메타에 세팅
    repo = _Repo()
    doc_store = _DocStore()
    skill_id = await CreateDraftSkillUseCase(repo, doc_store=doc_store).execute(
        owner_user_id=uuid4(),
        name="환불 알림",
        description="환불 시 슬랙 알림",
        node_spec_staging=_staging(),
        instructions="## When to use\n환불 요청 시.\n## Steps\n1. 알림",
    )

    # SkillDocument가 fake GCS에 저장됨 (use case가 생성한 skill_id로 식별 — ordering 해결)
    doc = doc_store.saved[skill_id]
    assert doc.skill_id == skill_id
    assert doc.name == "환불 알림"
    assert doc.description == "환불 시 슬랙 알림"
    assert doc.instructions.startswith("## When to use")

    # 어댑터가 반환한 gs:// URI가 메타데이터에 세팅됨 (호출부가 bucket 모름 → 반환값 사용)
    saved = repo.personal[skill_id]
    assert saved.skill_document_uri == f"gs://test-bucket/skills/{skill_id}/SKILL.md"


@pytest.mark.asyncio
async def test_create_draft_persists_source_document_id():
    # REQ-010 문서→빌더 핸드오프: 기반 문서 ID를 association 으로 보관
    repo = _Repo()
    doc_id = uuid4()
    skill_id = await CreateDraftSkillUseCase(repo).execute(
        owner_user_id=uuid4(),
        name="문서 기반 스킬",
        description="업로드한 명세서 기반",
        node_spec_staging=_staging(),
        source_document_id=doc_id,
    )
    assert repo.personal[skill_id].source_document_id == doc_id


@pytest.mark.asyncio
async def test_create_draft_source_document_id_defaults_none():
    # 미지정 시 association 없음 (직접 진입/seed 경로)
    repo = _Repo()
    skill_id = await CreateDraftSkillUseCase(repo).execute(
        owner_user_id=uuid4(),
        name="요약 스킬",
        description="문서 요약",
        node_spec_staging=_staging(),
    )
    assert repo.personal[skill_id].source_document_id is None


@pytest.mark.asyncio
async def test_create_draft_no_doc_store_skips_document_save():
    # doc_store 미주입 시 기존 동작 유지 — 문서 저장 없이 DRAFT만 생성 (seed/하위호환 경로)
    repo = _Repo()
    skill_id = await CreateDraftSkillUseCase(repo).execute(
        owner_user_id=uuid4(),
        name="요약 스킬",
        description="문서 요약",
        node_spec_staging=_staging(),
        instructions="## 무시됨 (store 없음)",
    )
    assert repo.personal[skill_id].skill_document_uri is None


@pytest.mark.asyncio
async def test_create_draft_doc_store_without_instructions_skips_save():
    # instructions 없으면(=None) doc_store가 있어도 저장 안 함
    repo = _Repo()
    doc_store = _DocStore()
    skill_id = await CreateDraftSkillUseCase(repo, doc_store=doc_store).execute(
        owner_user_id=uuid4(),
        name="요약 스킬",
        description="문서 요약",
        node_spec_staging=_staging(),
    )
    assert doc_store.saved == {}
    assert repo.personal[skill_id].skill_document_uri is None
