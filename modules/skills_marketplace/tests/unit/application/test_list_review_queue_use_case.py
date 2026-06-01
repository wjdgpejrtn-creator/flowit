"""ListReviewQueueUseCase — 관리자 리뷰 큐 인가(Admin only) + 조회 위임 테스트 (REQ-013)."""
from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from common_schemas.exceptions import AuthorizationError

from skills_marketplace.application.use_cases import ListReviewQueueUseCase
from skills_marketplace.domain.entities.marketplace_personal_skill import MarketplacePersonalSkill
from skills_marketplace.domain.value_objects.skill_state import SkillState


def _skill() -> MarketplacePersonalSkill:
    now = datetime.now(UTC)
    return MarketplacePersonalSkill(
        skill_id=uuid4(),
        owner_user_id=uuid4(),
        name="리뷰 대기 스킬",
        description="검토 요청됨",
        lifecycle_state=SkillState.REVIEW,
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_admin_lists_review_queue():
    repo = AsyncMock()
    repo.list_personal_by_state.return_value = [_skill()]
    use_case = ListReviewQueueUseCase(repo=repo)

    result = await use_case.execute(actor_role="Admin", limit=10, offset=0)

    assert len(result) == 1
    repo.list_personal_by_state.assert_awaited_once_with(
        SkillState.REVIEW, limit=10, offset=0
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["User", "team_manager", "company_manager"])
async def test_non_admin_rejected(role):
    repo = AsyncMock()
    use_case = ListReviewQueueUseCase(repo=repo)

    with pytest.raises(AuthorizationError):
        await use_case.execute(actor_role=role)

    repo.list_personal_by_state.assert_not_called()
