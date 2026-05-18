from __future__ import annotations

import pytest

from ai_agent.domain.entities.memory_file import MemoryFile, MemoryFileRef


class TestMemoryFileRef:
    def test_instantiation(self):
        ref = MemoryFileRef(filename="user_role.md", name="user-role", description="사용자 역할")
        assert ref.filename == "user_role.md"
        assert ref.name == "user-role"
        assert ref.description == "사용자 역할"

    def test_frozen(self):
        ref = MemoryFileRef(filename="a.md", name="a", description="desc")
        with pytest.raises(Exception):
            ref.name = "b"  # type: ignore[misc]


class TestMemoryFile:
    def test_instantiation(self):
        f = MemoryFile(
            filename="workflow_patterns.md",
            name="workflow-patterns",
            description="워크플로우 패턴",
            memory_type="feedback",
            body="슬랙 알림 선호",
        )
        assert f.memory_type == "feedback"
        assert f.body == "슬랙 알림 선호"

    def test_valid_memory_types(self):
        for mt in ("user", "feedback", "project", "reference"):
            f = MemoryFile(filename="f.md", name="n", description="d", memory_type=mt, body="")  # type: ignore[arg-type]
            assert f.memory_type == mt
