"""ListUserPersonalSkills / UpdatePersonalSkill / DeletePersonalSkill 유스케이스 단위 테스트.

personal skills 미리보기/편집 UI 백엔드 (REQ-013, 가원 요청). 인가(owner) + lifecycle(DRAFT) +
GCS 정리(삭제 시 doc_store.delete) 경계를 mock repo/doc_store로 검증.
"""
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from common_schemas.exceptions import AuthorizationError, NotFoundError, ValidationError

from skills_marketplace.application.use_cases import (
    DeletePersonalSkillUseCase,
    ListUserPersonalSkillsUseCase,
    UpdatePersonalSkillUseCase,
)
from skills_marketplace.domain.entities import MarketplacePersonalSkill
from skills_marketplace.domain.value_objects import SkillState


class _InMemorySkillRepo:
    def __init__(self) -> None:
        self.personal: dict[UUID, MarketplacePersonalSkill] = {}

    async def save_personal(self, skill):
        self.personal[skill.skill_id] = skill
        return skill

    async def get_personal(self, skill_id):
        return self.personal.get(skill_id)

    async def list_personal_by_user(self, user_id, lifecycle_state=None, limit=50, offset=0):
        rows = [s for s in self.personal.values() if s.owner_user_id == user_id]
        if lifecycle_state is not None:
            rows = [s for s in rows if SkillState(s.lifecycle_state) == lifecycle_state]
        rows.sort(key=lambda s: s.updated_at, reverse=True)
        return rows[offset : offset + limit]

    async def delete_personal(self, skill_id):
        self.personal.pop(skill_id, None)


class _SpyDocStore:
    def __init__(self) -> None:
        self.deleted: list[UUID] = []

    async def save(self, skill_id, document):
        return f"gs://bucket/skills/{skill_id}/SKILL.md"

    async def load(self, skill_id):
        return None

    async def delete(self, skill_id):
        self.deleted.append(skill_id)


def _personal(skill_id, owner_id, state=SkillState.DRAFT, *, uri=None, name="스킬", ts=None):
    now = ts or datetime.now(UTC)
    return MarketplacePersonalSkill(
        skill_id=skill_id,
        owner_user_id=owner_id,
        name=name,
        description="설명",
        lifecycle_state=state,
        skill_document_uri=uri,
        created_at=now,
        updated_at=now,
    )


# ── List ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_returns_only_owner_skills():
    repo = _InMemorySkillRepo()
    me, other = uuid4(), uuid4()
    await repo.save_personal(_personal(uuid4(), me))
    await repo.save_personal(_personal(uuid4(), me))
    await repo.save_personal(_personal(uuid4(), other))

    result = await ListUserPersonalSkillsUseCase(repo).execute(me)

    assert len(result) == 2
    assert all(s.owner_user_id == me for s in result)


@pytest.mark.asyncio
async def test_list_lifecycle_filter():
    repo = _InMemorySkillRepo()
    me = uuid4()
    await repo.save_personal(_personal(uuid4(), me, SkillState.DRAFT))
    await repo.save_personal(_personal(uuid4(), me, SkillState.PUBLISHED))

    drafts = await ListUserPersonalSkillsUseCase(repo).execute(me, lifecycle_state=SkillState.DRAFT)

    assert len(drafts) == 1
    assert SkillState(drafts[0].lifecycle_state) == SkillState.DRAFT


@pytest.mark.asyncio
async def test_list_orders_by_updated_at_desc():
    repo = _InMemorySkillRepo()
    me = uuid4()
    old = _personal(uuid4(), me, name="old", ts=datetime.now(UTC) - timedelta(hours=1))
    new = _personal(uuid4(), me, name="new", ts=datetime.now(UTC))
    await repo.save_personal(old)
    await repo.save_personal(new)

    result = await ListUserPersonalSkillsUseCase(repo).execute(me)

    assert [s.name for s in result] == ["new", "old"]


# ── Update ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_update_changes_fields_by_owner():
    repo = _InMemorySkillRepo()
    me, sid = uuid4(), uuid4()
    await repo.save_personal(_personal(sid, me))

    updated = await UpdatePersonalSkillUseCase(repo).execute(
        sid, me, name="새이름", description="새설명", tags=["a", "b"]
    )

    assert updated.name == "새이름"
    assert updated.description == "새설명"
    assert updated.tags == ["a", "b"]
    assert (await repo.get_personal(sid)).name == "새이름"


@pytest.mark.asyncio
async def test_update_partial_only_given_fields():
    repo = _InMemorySkillRepo()
    me, sid = uuid4(), uuid4()
    await repo.save_personal(_personal(sid, me, name="원래"))

    updated = await UpdatePersonalSkillUseCase(repo).execute(sid, me, description="설명만변경")

    assert updated.name == "원래"  # 미변경
    assert updated.description == "설명만변경"


@pytest.mark.asyncio
async def test_update_rejects_non_owner():
    repo = _InMemorySkillRepo()
    owner, sid = uuid4(), uuid4()
    await repo.save_personal(_personal(sid, owner, name="원래"))

    with pytest.raises(AuthorizationError):
        await UpdatePersonalSkillUseCase(repo).execute(sid, uuid4(), name="해킹")
    assert (await repo.get_personal(sid)).name == "원래"


@pytest.mark.asyncio
async def test_update_not_found():
    repo = _InMemorySkillRepo()
    with pytest.raises(NotFoundError):
        await UpdatePersonalSkillUseCase(repo).execute(uuid4(), uuid4(), name="x")


@pytest.mark.asyncio
async def test_update_non_draft_rejected():
    repo = _InMemorySkillRepo()
    me, sid = uuid4(), uuid4()
    await repo.save_personal(_personal(sid, me, SkillState.PUBLISHED))

    with pytest.raises(ValidationError):
        await UpdatePersonalSkillUseCase(repo).execute(sid, me, name="수정시도")


@pytest.mark.asyncio
async def test_update_blank_name_rejected():
    repo = _InMemorySkillRepo()
    me, sid = uuid4(), uuid4()
    await repo.save_personal(_personal(sid, me))

    with pytest.raises(ValidationError):
        await UpdatePersonalSkillUseCase(repo).execute(sid, me, name="   ")


@pytest.mark.asyncio
async def test_update_no_changes_returns_skill():
    repo = _InMemorySkillRepo()
    me, sid = uuid4(), uuid4()
    await repo.save_personal(_personal(sid, me, name="그대로"))

    result = await UpdatePersonalSkillUseCase(repo).execute(sid, me)

    assert result.name == "그대로"


# ── Delete ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_delete_removes_db_and_gcs():
    repo = _InMemorySkillRepo()
    doc = _SpyDocStore()
    me, sid = uuid4(), uuid4()
    await repo.save_personal(_personal(sid, me, uri="gs://bucket/skills/x/SKILL.md"))

    await DeletePersonalSkillUseCase(repo, doc).execute(sid, me)

    assert await repo.get_personal(sid) is None
    assert doc.deleted == [sid]  # GCS도 정리됨


@pytest.mark.asyncio
async def test_delete_without_doc_store_db_only():
    repo = _InMemorySkillRepo()
    me, sid = uuid4(), uuid4()
    await repo.save_personal(_personal(sid, me, uri="gs://bucket/skills/x/SKILL.md"))

    await DeletePersonalSkillUseCase(repo).execute(sid, me)  # doc_store 미주입

    assert await repo.get_personal(sid) is None


@pytest.mark.asyncio
async def test_delete_skips_gcs_when_no_document_uri():
    repo = _InMemorySkillRepo()
    doc = _SpyDocStore()
    me, sid = uuid4(), uuid4()
    await repo.save_personal(_personal(sid, me, uri=None))  # 문서 없음

    await DeletePersonalSkillUseCase(repo, doc).execute(sid, me)

    assert await repo.get_personal(sid) is None
    assert doc.deleted == []  # 문서 URI 없으면 GCS delete 호출 안 함


@pytest.mark.asyncio
async def test_delete_rejects_non_owner():
    repo = _InMemorySkillRepo()
    doc = _SpyDocStore()
    owner, sid = uuid4(), uuid4()
    await repo.save_personal(_personal(sid, owner, uri="gs://b/x/SKILL.md"))

    with pytest.raises(AuthorizationError):
        await DeletePersonalSkillUseCase(repo, doc).execute(sid, uuid4())
    assert await repo.get_personal(sid) is not None  # 미삭제
    assert doc.deleted == []


@pytest.mark.asyncio
async def test_delete_not_found():
    repo = _InMemorySkillRepo()
    with pytest.raises(NotFoundError):
        await DeletePersonalSkillUseCase(repo).execute(uuid4(), uuid4())


@pytest.mark.asyncio
async def test_delete_non_draft_rejected():
    repo = _InMemorySkillRepo()
    doc = _SpyDocStore()
    me, sid = uuid4(), uuid4()
    await repo.save_personal(_personal(sid, me, SkillState.PUBLISHED, uri="gs://b/x/SKILL.md"))

    with pytest.raises(ValidationError):
        await DeletePersonalSkillUseCase(repo, doc).execute(sid, me)
    assert await repo.get_personal(sid) is not None
    assert doc.deleted == []
