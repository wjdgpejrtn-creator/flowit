"""GetMarketplaceSkillDocumentUseCase 단위 테스트.

마켓플레이스(team/company) 스킬 지침서(SKILL.md) 조회. 단건 메타 조회와 동일 PUBLISHED 게이트
통과 후 GCS load. 미게시→404(doc_store 미호출), 지침서 없음→404, personal→400 검증.
"""
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from common_schemas import SkillDocument
from common_schemas.exceptions import NotFoundError, ValidationError

from skills_marketplace.application.use_cases import GetMarketplaceSkillDocumentUseCase
from skills_marketplace.domain.entities import MarketplaceCompanySkill
from skills_marketplace.domain.value_objects import SkillScope, SkillState


def _company(skill_id, state=SkillState.PUBLISHED):
    now = datetime.now(UTC)
    return MarketplaceCompanySkill(
        skill_id=skill_id, author_id=uuid4(), name="전사 스킬", description="설명",
        lifecycle_state=state, created_at=now, updated_at=now,
    )


class _Repo:
    def __init__(self, company=None):
        self._company = company

    async def get_company(self, skill_id):
        return self._company

    async def get_team(self, skill_id):
        return None


class _DocStore:
    def __init__(self, doc=None):
        self._doc = doc
        self.load_calls = 0

    async def load(self, skill_id):
        self.load_calls += 1
        return self._doc


@pytest.mark.asyncio
async def test_published_with_document_returns():
    sid = uuid4()
    doc = SkillDocument(skill_id=sid, name="전사 스킬", description="설명", instructions="# 사용법\n단계...")
    uc = GetMarketplaceSkillDocumentUseCase(_Repo(company=_company(sid)), _DocStore(doc=doc))
    result = await uc.execute(scope=SkillScope.COMPANY, skill_id=sid)
    assert result.instructions.startswith("# 사용법")


@pytest.mark.asyncio
async def test_published_without_document_404():
    sid = uuid4()
    uc = GetMarketplaceSkillDocumentUseCase(_Repo(company=_company(sid)), _DocStore(doc=None))
    with pytest.raises(NotFoundError):
        await uc.execute(scope=SkillScope.COMPANY, skill_id=sid)


@pytest.mark.asyncio
async def test_non_published_404_without_loading_doc():
    # 미게시 스킬은 게이트에서 404 — GCS load까지 가지 않아야(지침서 노출 차단 + 불필요 IO 방지)
    sid = uuid4()
    store = _DocStore(doc=SkillDocument(skill_id=sid, name="x", description="y", instructions="z"))
    uc = GetMarketplaceSkillDocumentUseCase(_Repo(company=_company(sid, state=SkillState.DRAFT)), store)
    with pytest.raises(NotFoundError):
        await uc.execute(scope=SkillScope.COMPANY, skill_id=sid)
    assert store.load_calls == 0


@pytest.mark.asyncio
async def test_personal_scope_rejected():
    uc = GetMarketplaceSkillDocumentUseCase(_Repo(), _DocStore())
    with pytest.raises(ValidationError):
        await uc.execute(scope=SkillScope.PERSONAL, skill_id=uuid4())
