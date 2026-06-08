"""ArchivePersonalSkill / RestorePersonalSkill 유스케이스 단위 테스트 (REQ-013).

마켓플레이스 보관/복원 — owner 인가 + lifecycle 상태 가드(PUBLISHED↔ARCHIVED) 경계를
mock repo로 검증. archive=PUBLISHED→ARCHIVED, restore=ARCHIVED→PUBLISHED.
"""
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from common_schemas.exceptions import AuthorizationError, NotFoundError, ValidationError

from skills_marketplace.application.use_cases import (
    ArchivePersonalSkillUseCase,
    RestorePersonalSkillUseCase,
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


def _personal(skill_id, owner_id, state):
    now = datetime.now(UTC)
    return MarketplacePersonalSkill(
        skill_id=skill_id,
        owner_user_id=owner_id,
        name="스킬",
        description="설명",
        lifecycle_state=state,
        created_at=now,
        updated_at=now,
    )


# ── Archive (PUBLISHED → ARCHIVED) ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_archive_published_by_owner():
    repo = _InMemorySkillRepo()
    me, sid = uuid4(), uuid4()
    await repo.save_personal(_personal(sid, me, SkillState.PUBLISHED))

    await ArchivePersonalSkillUseCase(repo).execute(sid, me)

    assert SkillState((await repo.get_personal(sid)).lifecycle_state) == SkillState.ARCHIVED


@pytest.mark.asyncio
async def test_archive_rejects_non_owner():
    repo = _InMemorySkillRepo()
    owner, sid = uuid4(), uuid4()
    await repo.save_personal(_personal(sid, owner, SkillState.PUBLISHED))

    with pytest.raises(AuthorizationError):
        await ArchivePersonalSkillUseCase(repo).execute(sid, uuid4())
    # 상태 미변경
    assert SkillState((await repo.get_personal(sid)).lifecycle_state) == SkillState.PUBLISHED


@pytest.mark.asyncio
async def test_archive_not_found():
    repo = _InMemorySkillRepo()
    with pytest.raises(NotFoundError):
        await ArchivePersonalSkillUseCase(repo).execute(uuid4(), uuid4())


@pytest.mark.asyncio
async def test_archive_rejects_non_published_state():
    """DRAFT 등 PUBLISHED 외 상태는 보관 불가 (E-SKILL-002)."""
    repo = _InMemorySkillRepo()
    me, sid = uuid4(), uuid4()
    await repo.save_personal(_personal(sid, me, SkillState.DRAFT))

    with pytest.raises(ValidationError):
        await ArchivePersonalSkillUseCase(repo).execute(sid, me)
    assert SkillState((await repo.get_personal(sid)).lifecycle_state) == SkillState.DRAFT


# ── Restore (ARCHIVED → PUBLISHED) ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_restore_archived_by_owner():
    repo = _InMemorySkillRepo()
    me, sid = uuid4(), uuid4()
    await repo.save_personal(_personal(sid, me, SkillState.ARCHIVED))

    await RestorePersonalSkillUseCase(repo).execute(sid, me)

    assert SkillState((await repo.get_personal(sid)).lifecycle_state) == SkillState.PUBLISHED


@pytest.mark.asyncio
async def test_restore_rejects_non_owner():
    repo = _InMemorySkillRepo()
    owner, sid = uuid4(), uuid4()
    await repo.save_personal(_personal(sid, owner, SkillState.ARCHIVED))

    with pytest.raises(AuthorizationError):
        await RestorePersonalSkillUseCase(repo).execute(sid, uuid4())
    assert SkillState((await repo.get_personal(sid)).lifecycle_state) == SkillState.ARCHIVED


@pytest.mark.asyncio
async def test_restore_not_found():
    repo = _InMemorySkillRepo()
    with pytest.raises(NotFoundError):
        await RestorePersonalSkillUseCase(repo).execute(uuid4(), uuid4())


@pytest.mark.asyncio
async def test_restore_rejects_non_archived_state():
    """PUBLISHED 등 ARCHIVED 외 상태는 복원 불가 (E-SKILL-002)."""
    repo = _InMemorySkillRepo()
    me, sid = uuid4(), uuid4()
    await repo.save_personal(_personal(sid, me, SkillState.PUBLISHED))

    with pytest.raises(ValidationError):
        await RestorePersonalSkillUseCase(repo).execute(sid, me)


# ── 왕복 (archive → restore) ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_archive_then_restore_roundtrip():
    repo = _InMemorySkillRepo()
    me, sid = uuid4(), uuid4()
    await repo.save_personal(_personal(sid, me, SkillState.PUBLISHED))

    await ArchivePersonalSkillUseCase(repo).execute(sid, me)
    await RestorePersonalSkillUseCase(repo).execute(sid, me)

    assert SkillState((await repo.get_personal(sid)).lifecycle_state) == SkillState.PUBLISHED
