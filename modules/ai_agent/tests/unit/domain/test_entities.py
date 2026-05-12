from uuid import uuid4

import pytest

from ai_agent.domain.entities import ConversationMessage, MemoryEntry


class TestMemoryEntrySSOT:
    """MemoryEntry는 common_schemas의 SSOT를 재노출만 한다."""

    def test_is_common_schemas_class(self):
        from common_schemas import MemoryEntry as CSMemoryEntry

        assert MemoryEntry is CSMemoryEntry


class TestMemoryEntry:
    def test_create_without_session(self):
        entry = MemoryEntry(
            user_id=uuid4(),
            memory_type="preference",
            content="슬랙 알림을 항상 포함",
        )
        assert entry.source_session_id is None
        assert entry.metadata == {}

    def test_create_with_session(self):
        sid = uuid4()
        entry = MemoryEntry(
            user_id=uuid4(),
            memory_type="workflow_pattern",
            content="주간 보고서 자동화",
            source_session_id=sid,
        )
        assert entry.source_session_id == sid

    def test_is_ephemeral_empty(self):
        entry = MemoryEntry(user_id=uuid4(), memory_type="summary", content="   ")
        assert entry.is_ephemeral() is True

    def test_is_ephemeral_has_content(self):
        entry = MemoryEntry(user_id=uuid4(), memory_type="preference", content="구글 드라이브 기본")
        assert entry.is_ephemeral() is False

    def test_immutable(self):
        entry = MemoryEntry(user_id=uuid4(), memory_type="preference", content="테스트")
        with pytest.raises(Exception):
            entry.content = "변경 시도"


class TestConversationMessage:
    def test_create(self):
        msg = ConversationMessage(role="user", content="안녕하세요")
        assert msg.role == "user"
        assert msg.timestamp is not None
        assert msg.metadata is None

    def test_all_roles(self):
        for role in ("user", "assistant", "system"):
            msg = ConversationMessage(role=role, content="test")
            assert msg.role == role

    def test_immutable(self):
        msg = ConversationMessage(role="user", content="test")
        with pytest.raises(Exception):
            msg.content = "변경"
