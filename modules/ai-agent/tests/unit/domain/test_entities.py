from uuid import uuid4

import pytest

from ai_agent.domain.entities import CorrectionPattern, MemoryEntry


class TestMemoryEntry:
    def test_create(self):
        entry = MemoryEntry(
            user_id=uuid4(),
            memory_type="preference",
            content="슬랙 알림을 항상 포함",
            source_session_id=uuid4(),
        )
        assert entry.entry_id is not None
        assert entry.created_at is not None

    def test_is_ephemeral_empty(self):
        entry = MemoryEntry(
            user_id=uuid4(),
            memory_type="summary",
            content="   ",
            source_session_id=uuid4(),
        )
        assert entry.is_ephemeral() is True

    def test_is_ephemeral_has_content(self):
        entry = MemoryEntry(
            user_id=uuid4(),
            memory_type="preference",
            content="구글 드라이브를 기본 저장소로",
            source_session_id=uuid4(),
        )
        assert entry.is_ephemeral() is False

    def test_immutable(self):
        entry = MemoryEntry(
            user_id=uuid4(),
            memory_type="preference",
            content="테스트",
            source_session_id=uuid4(),
        )
        with pytest.raises(Exception):
            entry.content = "변경 시도"


class TestCorrectionPattern:
    def test_create_defaults(self):
        pattern = CorrectionPattern(
            user_id=uuid4(),
            original="슬렉",
            corrected="슬랙",
        )
        assert pattern.frequency == 1
        assert pattern.is_recurring() is False

    def test_is_recurring_true(self):
        pattern = CorrectionPattern(
            user_id=uuid4(),
            original="슬렉",
            corrected="슬랙",
            frequency=3,
        )
        assert pattern.is_recurring() is True

    def test_immutable(self):
        pattern = CorrectionPattern(
            user_id=uuid4(),
            original="a",
            corrected="b",
        )
        with pytest.raises(Exception):
            pattern.frequency = 99
