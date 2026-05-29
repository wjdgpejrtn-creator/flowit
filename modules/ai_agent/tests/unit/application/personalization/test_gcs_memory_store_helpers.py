"""GCS adapter 내부 헬퍼 함수 unit test — GCS 호출 없이 순수 로직만 검증."""
from __future__ import annotations

import pytest

from ai_agent.adapters.memory.gcs_memory_store import (
    _parse_index,
    _parse_md_file,
    _serialize_index,
    _serialize_md_file,
)
from ai_agent.domain.entities.memory_file import MemoryFile, MemoryFileRef


class TestIndexParsing:
    def test_parse_empty_memory_md(self):
        assert _parse_index("# Memory Index\n\n") == []

    def test_parse_single_ref(self):
        content = "# Memory Index\n\n- [user-role](user_role.md) — 사용자 역할 설명\n"
        refs = _parse_index(content)
        assert len(refs) == 1
        assert refs[0].name == "user-role"
        assert refs[0].filename == "user_role.md"
        assert refs[0].description == "사용자 역할 설명"

    def test_parse_multiple_refs(self):
        content = (
            "# Memory Index\n\n"
            "- [user-role](user_role.md) — 역할\n"
            "- [workflow-patterns](workflow_patterns.md) — 패턴\n"
        )
        refs = _parse_index(content)
        assert len(refs) == 2

    def test_non_list_lines_ignored(self):
        content = "# Memory Index\n\n일부 설명 텍스트\n- [a](a.md) — desc\n"
        refs = _parse_index(content)
        assert len(refs) == 1


class TestIndexSerialization:
    def test_serialize_empty(self):
        result = _serialize_index([])
        assert result.startswith("# Memory Index")

    def test_round_trip(self):
        refs = [
            MemoryFileRef(filename="user_role.md", name="user-role", description="역할"),
            MemoryFileRef(filename="feedback.md", name="feedback", description="피드백"),
        ]
        serialized = _serialize_index(refs)
        parsed = _parse_index(serialized)
        assert len(parsed) == 2
        assert parsed[0].filename == "user_role.md"
        assert parsed[1].name == "feedback"


class TestMdFileParsing:
    def test_parse_well_formed_frontmatter(self):
        raw = (
            "---\n"
            "name: user-role\n"
            "description: 사용자 역할\n"
            "metadata:\n"
            "  type: user\n"
            "---\n\n"
            "본문 내용입니다.\n"
        )
        f = _parse_md_file("user_role.md", raw)
        assert f.name == "user-role"
        assert f.description == "사용자 역할"
        assert f.memory_type == "user"
        assert "본문" in f.body

    def test_parse_no_frontmatter(self):
        raw = "내용만 있는 파일\n"
        f = _parse_md_file("notes.md", raw)
        assert f.filename == "notes.md"
        assert f.name == "notes"
        assert f.body == raw

    def test_parse_incomplete_frontmatter(self):
        raw = "--- 시작만 있는 파일\n본문\n"
        f = _parse_md_file("x.md", raw)
        assert f.body is not None


class TestMdFileSerialization:
    def test_round_trip(self):
        original = MemoryFile(
            filename="workflow_patterns.md",
            name="workflow-patterns",
            description="워크플로우 패턴",
            memory_type="feedback",
            body="슬랙 알림을 선호한다.",
        )
        serialized = _serialize_md_file(original)
        parsed = _parse_md_file("workflow_patterns.md", serialized)
        assert parsed.name == original.name
        assert parsed.description == original.description
        assert parsed.memory_type == original.memory_type
        assert original.body in parsed.body
