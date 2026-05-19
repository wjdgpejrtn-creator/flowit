from __future__ import annotations

import pytest

from common_schemas.exceptions import ValidationError
from storage.marketplace.domain.skill_lifecycle import SkillLifecycle, SkillState


class TestSkillLifecycle:
    def test_draft_to_review(self) -> None:
        result = SkillLifecycle.transition(SkillState.DRAFT, SkillState.REVIEW)
        assert result == SkillState.REVIEW

    def test_review_to_approved(self) -> None:
        result = SkillLifecycle.transition(SkillState.REVIEW, SkillState.APPROVED)
        assert result == SkillState.APPROVED

    def test_review_to_draft_rejected(self) -> None:
        result = SkillLifecycle.transition(SkillState.REVIEW, SkillState.DRAFT)
        assert result == SkillState.DRAFT

    def test_approved_to_published(self) -> None:
        result = SkillLifecycle.transition(SkillState.APPROVED, SkillState.PUBLISHED)
        assert result == SkillState.PUBLISHED

    def test_published_to_archived(self) -> None:
        result = SkillLifecycle.transition(SkillState.PUBLISHED, SkillState.ARCHIVED)
        assert result == SkillState.ARCHIVED

    def test_archived_to_draft(self) -> None:
        result = SkillLifecycle.transition(SkillState.ARCHIVED, SkillState.DRAFT)
        assert result == SkillState.DRAFT

    def test_invalid_draft_to_published(self) -> None:
        with pytest.raises(ValidationError, match="Invalid transition"):
            SkillLifecycle.transition(SkillState.DRAFT, SkillState.PUBLISHED)

    def test_invalid_published_to_draft(self) -> None:
        with pytest.raises(ValidationError, match="Invalid transition"):
            SkillLifecycle.transition(SkillState.PUBLISHED, SkillState.DRAFT)

    def test_full_lifecycle(self) -> None:
        state = SkillState.DRAFT
        state = SkillLifecycle.transition(state, SkillState.REVIEW)
        state = SkillLifecycle.transition(state, SkillState.APPROVED)
        state = SkillLifecycle.transition(state, SkillState.PUBLISHED)
        state = SkillLifecycle.transition(state, SkillState.ARCHIVED)
        assert state == SkillState.ARCHIVED

    def test_can_transition(self) -> None:
        assert SkillLifecycle.can_transition(SkillState.DRAFT, SkillState.REVIEW) is True
        assert SkillLifecycle.can_transition(SkillState.DRAFT, SkillState.PUBLISHED) is False
