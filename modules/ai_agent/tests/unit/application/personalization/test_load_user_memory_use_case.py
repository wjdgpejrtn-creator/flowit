from __future__ import annotations

import pytest
from unittest.mock import AsyncMock
from uuid import uuid4

from ai_agent.application.agents.personalization.load_user_memory_use_case import (
    LoadUserMemoryUseCase,
)
from ai_agent.domain.entities.memory_file import MemoryFile, MemoryFileRef
from ai_agent.domain.ports.personal_memory_store import PersonalMemoryStore


def _make_ref(name: str) -> MemoryFileRef:
    return MemoryFileRef(filename=f"{name}.md", name=name, description=f"{name} desc")


def _make_file(name: str, memory_type: str = "feedback") -> MemoryFile:
    return MemoryFile(
        filename=f"{name}.md",
        name=name,
        description=f"{name} desc",
        memory_type=memory_type,  # type: ignore[arg-type]
        body=f"{name} 내용",
    )


class TestLoadUserMemoryUseCase:
    @pytest.mark.asyncio
    async def test_empty_index_returns_empty(self):
        store = AsyncMock(spec=PersonalMemoryStore)
        store.load_index.return_value = []
        uc = LoadUserMemoryUseCase(store)
        result = await uc.execute(uuid4())
        assert result == []

    @pytest.mark.asyncio
    async def test_loads_all_files_from_index(self):
        store = AsyncMock(spec=PersonalMemoryStore)
        uid = uuid4()
        store.load_index.return_value = [_make_ref("user_role"), _make_ref("workflow_patterns")]
        store.load_file.side_effect = [
            _make_file("user_role", "user"),
            _make_file("workflow_patterns", "feedback"),
        ]
        uc = LoadUserMemoryUseCase(store)
        result = await uc.execute(uid)
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_missing_file_is_skipped(self):
        store = AsyncMock(spec=PersonalMemoryStore)
        uid = uuid4()
        store.load_index.return_value = [_make_ref("missing"), _make_ref("present")]
        store.load_file.side_effect = [
            FileNotFoundError,
            _make_file("present"),
        ]
        uc = LoadUserMemoryUseCase(store)
        result = await uc.execute(uid)
        assert len(result) == 1
        assert "present" in result[0].metadata.get("name", "")

    @pytest.mark.asyncio
    async def test_content_maps_to_memory_entry(self):
        store = AsyncMock(spec=PersonalMemoryStore)
        uid = uuid4()
        store.load_index.return_value = [_make_ref("workflow_patterns")]
        store.load_file.return_value = _make_file("workflow_patterns", "feedback")
        uc = LoadUserMemoryUseCase(store)
        result = await uc.execute(uid)
        assert len(result) == 1
        assert result[0].content == "workflow_patterns 내용"
