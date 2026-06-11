from datetime import UTC, datetime
from uuid import uuid4

import pytest
from common_schemas import SkillDocument

from skills_marketplace.application.use_cases import (
    PromoteToCompanyUseCase,
    PromoteToTeamUseCase,
    SearchSkillsUseCase,
)
from skills_marketplace.domain.entities import MarketplacePersonalSkill
from skills_marketplace.domain.value_objects import SkillScope, SkillState


class _InMemoryDocStore:
    """SkillDocumentStore ABC In-Memory 구현 (테스트 전용) — GCS 키처럼 skill_id로 색인."""

    def __init__(self) -> None:
        self.docs: dict = {}

    async def save(self, skill_id, document) -> str:
        self.docs[skill_id] = document
        return f"gs://test-bucket/skills/{skill_id}/SKILL.md"

    async def load(self, skill_id):
        return self.docs.get(skill_id)

    async def delete(self, skill_id) -> None:
        self.docs.pop(skill_id, None)


def _doc(skill_id) -> SkillDocument:
    return SkillDocument(
        skill_id=skill_id,
        name="환불 자동화",
        description="환불 요청 처리 스킬",
        instructions="## 단계\n1. 요청 확인\n2. 승인",
        composer_instructions="LLM 노드 + Email 노드 필수",
    )


class _InMemorySkillRepo:
    """inline 헬퍼 — SkillRepository ABC In-Memory 구현 (테스트 전용)."""

    def __init__(self) -> None:
        self.personal: dict = {}
        self.team: dict = {}
        self.company: dict = {}

    async def save_personal(self, skill):
        self.personal[skill.skill_id] = skill
        return skill

    async def save_team(self, skill):
        self.team[skill.skill_id] = skill
        return skill

    async def save_company(self, skill):
        self.company[skill.skill_id] = skill
        return skill

    async def get_personal(self, skill_id):
        return self.personal.get(skill_id)

    async def get_team(self, skill_id):
        return self.team.get(skill_id)

    async def get_company(self, skill_id):
        return self.company.get(skill_id)

    async def search(self, query_embedding, scope, limit=10, include_promoted=False,
                     lifecycle_state=None, owner_user_id=None, max_distance=None):
        store = {
            SkillScope.PERSONAL: self.personal,
            SkillScope.TEAM: self.team,
            SkillScope.COMPANY: self.company,
        }[scope]
        results = list(store.values())
        if not include_promoted:
            results = [
                s
                for s in results
                if getattr(s, "promoted_to_team_id", None) is None
                and getattr(s, "promoted_to_company_id", None) is None
            ]
        return results[:limit]


def _personal(skill_id, owner_id):
    now = datetime.now(UTC)
    return MarketplacePersonalSkill(
        skill_id=skill_id,
        owner_user_id=owner_id,
        name="환불 자동화",
        description="환불 요청 처리 스킬",
        node_definition_id=uuid4(),
        lifecycle_state=SkillState.PUBLISHED,
        tags=["refund", "cs"],
        version="1.0.0",
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_promote_personal_to_team_creates_team_skill():
    repo = _InMemorySkillRepo()
    pid, owner = uuid4(), uuid4()
    await repo.save_personal(_personal(pid, owner))

    team_id = uuid4()
    new_id = await PromoteToTeamUseCase(repo).execute(pid, team_id)

    team = await repo.get_team(new_id)
    assert team is not None
    assert team.team_id == team_id
    assert team.author_id == owner          # 원작성자 승계
    assert team.promoted_from == pid         # 승격 역추적
    assert team.name == "환불 자동화"        # 메타 승계
    assert team.lifecycle_state == SkillState.DRAFT  # 승격 = 재심사 리셋 (게시상태 비승계, 조장 리뷰 #98)
    assert team.tags == ["refund", "cs"]

    # 승격 = 복제(원본 유지) — 원본 personal에 promoted_to_team_id 마킹
    origin = await repo.get_personal(pid)
    assert origin is not None
    assert origin.promoted_to_team_id == new_id


@pytest.mark.asyncio
async def test_search_excludes_promoted_origin_by_default():
    """승격 완료 원본은 search 기본값(include_promoted=False)에서 제외 (중복 노출 방지, 조장 리뷰 #98)."""
    repo = _InMemorySkillRepo()
    pid, owner, team_id = uuid4(), uuid4(), uuid4()
    await repo.save_personal(_personal(pid, owner))

    # 승격 전: personal 검색에 노출
    before = await repo.search([0.1] * 768, SkillScope.PERSONAL)
    assert len(before) == 1

    await PromoteToTeamUseCase(repo).execute(pid, team_id)

    # 승격 후: 기본 검색에서 원본 제외 / include_promoted=True면 포함
    after = await repo.search([0.1] * 768, SkillScope.PERSONAL)
    assert after == []
    assert len(await repo.search([0.1] * 768, SkillScope.PERSONAL, include_promoted=True)) == 1


@pytest.mark.asyncio
async def test_promote_team_to_company_creates_company_skill():
    repo = _InMemorySkillRepo()
    pid, owner, team_id = uuid4(), uuid4(), uuid4()
    await repo.save_personal(_personal(pid, owner))
    team_skill_id = await PromoteToTeamUseCase(repo).execute(pid, team_id)

    company_id = await PromoteToCompanyUseCase(repo).execute(team_skill_id)

    company = await repo.get_company(company_id)
    assert company is not None
    assert company.author_id == owner
    assert company.promoted_from == team_skill_id
    assert company.lifecycle_state == SkillState.DRAFT  # 재심사 리셋
    # 원본 team에 promoted_to_company_id 마킹 (검색 기본 제외)
    origin_team = await repo.get_team(team_skill_id)
    assert origin_team is not None
    assert origin_team.promoted_to_company_id == company_id


@pytest.mark.asyncio
async def test_promote_nonexistent_personal_raises():
    from common_schemas.exceptions import NotFoundError

    repo = _InMemorySkillRepo()
    with pytest.raises(NotFoundError):
        await PromoteToTeamUseCase(repo).execute(uuid4(), uuid4())


@pytest.mark.asyncio
async def test_search_delegates_to_repo():
    repo = _InMemorySkillRepo()
    pid, owner = uuid4(), uuid4()
    await repo.save_personal(_personal(pid, owner))

    results = await SearchSkillsUseCase(repo).execute([0.1] * 768, SkillScope.PERSONAL, limit=5)
    assert len(results) == 1
    assert results[0].skill_id == pid


@pytest.mark.asyncio
async def test_promote_to_team_copies_document_to_new_skill_id():
    """승격=복제 — 지침서(SKILL.md/COMPOSER.md)를 신규 skill_id로 GCS 복제하고 URI를 갱신한다.

    GCS 키가 skill_id 결정적이라 문자열 URI만 승계하면 신규 skill_id 경로에 객체가 없어 404가 난다.
    """
    repo = _InMemorySkillRepo()
    doc_store = _InMemoryDocStore()
    pid, owner, team_id = uuid4(), uuid4(), uuid4()
    await repo.save_personal(_personal(pid, owner))
    await doc_store.save(pid, _doc(pid))  # 원본 personal 지침서

    new_id = await PromoteToTeamUseCase(repo, doc_store=doc_store).execute(pid, team_id)

    # 신규 skill_id 경로에 지침서가 복제돼 load 가능
    copied = await doc_store.load(new_id)
    assert copied is not None
    assert copied.instructions == "## 단계\n1. 요청 확인\n2. 승인"
    assert copied.composer_instructions == "LLM 노드 + Email 노드 필수"
    # 복사본 메타의 URI는 신규 skill_id 경로를 가리킨다 (원본 URI 승계 아님)
    team = await repo.get_team(new_id)
    assert team.skill_document_uri == f"gs://test-bucket/skills/{new_id}/SKILL.md"


@pytest.mark.asyncio
async def test_promote_chain_personal_to_company_copies_document_each_hop():
    repo = _InMemorySkillRepo()
    doc_store = _InMemoryDocStore()
    pid, owner, team_id = uuid4(), uuid4(), uuid4()
    await repo.save_personal(_personal(pid, owner))
    await doc_store.save(pid, _doc(pid))

    team_id_new = await PromoteToTeamUseCase(repo, doc_store=doc_store).execute(pid, team_id)
    company_id = await PromoteToCompanyUseCase(repo, doc_store=doc_store).execute(team_id_new)

    # 매 홉마다 신규 skill_id 경로에 지침서 존재
    assert await doc_store.load(team_id_new) is not None
    company_doc = await doc_store.load(company_id)
    assert company_doc is not None
    assert company_doc.instructions == "## 단계\n1. 요청 확인\n2. 승인"
    company = await repo.get_company(company_id)
    assert company.skill_document_uri == f"gs://test-bucket/skills/{company_id}/SKILL.md"


@pytest.mark.asyncio
async def test_promote_without_doc_store_is_non_fatal():
    """doc_store 미주입(하위호환) 시 fallback URI 승계 + 승격은 정상 진행."""
    repo = _InMemorySkillRepo()
    pid, owner, team_id = uuid4(), uuid4(), uuid4()
    origin = _personal(pid, owner).model_copy(update={"skill_document_uri": "gs://b/skills/x/SKILL.md"})
    await repo.save_personal(origin)

    new_id = await PromoteToTeamUseCase(repo).execute(pid, team_id)  # doc_store=None

    team = await repo.get_team(new_id)
    assert team is not None
    assert team.skill_document_uri == "gs://b/skills/x/SKILL.md"  # fallback 승계


@pytest.mark.asyncio
async def test_promote_with_no_source_document_keeps_fallback():
    """doc_store는 있으나 원본 지침서가 없으면(수동 생성) fallback URI 유지(non-fatal)."""
    repo = _InMemorySkillRepo()
    doc_store = _InMemoryDocStore()  # 비어 있음
    pid, owner, team_id = uuid4(), uuid4(), uuid4()
    await repo.save_personal(_personal(pid, owner))  # skill_document_uri=None

    new_id = await PromoteToTeamUseCase(repo, doc_store=doc_store).execute(pid, team_id)

    team = await repo.get_team(new_id)
    assert team.skill_document_uri is None
    assert await doc_store.load(new_id) is None  # 복제할 원본이 없으니 새 경로도 비어 있음
