from __future__ import annotations

import pytest
from datetime import timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

from common_schemas import WorkflowSchema
from common_schemas.workflow import NodeInstance, Position

from ai_agent.application.agents.personalization.update_user_memory_use_case import (
    UpdateUserMemoryUseCase,
    _MemoryUpdateResult,
    _MemoryUpdateSpec,
)
from ai_agent.domain.entities.memory_file import MemoryFile, MemoryFileRef
from ai_agent.domain.ports.llm_port import LLMPort
from ai_agent.domain.ports.personal_memory_store import PersonalMemoryStore


def _make_workflow(node_count: int = 1) -> WorkflowSchema:
    nodes = [
        NodeInstance(instance_id=uuid4(), node_id=uuid4(), parameters={}, position=Position(x=0, y=0))
        for _ in range(node_count)
    ]
    return WorkflowSchema(
        workflow_id=uuid4(),
        name="테스트 워크플로우",
        scope="private",
        is_draft=False,
        nodes=nodes,
        connections=[],
        owner_user_id=uuid4(),
    )


def _make_llm_result(specs: list[_MemoryUpdateSpec]) -> _MemoryUpdateResult:
    return _MemoryUpdateResult(updates=specs)


def _make_store_with(refs: list[MemoryFileRef], files: dict[str, MemoryFile]) -> AsyncMock:
    store = AsyncMock(spec=PersonalMemoryStore)
    store.load_index.return_value = refs

    async def _load_file(user_id, filename):
        if filename in files:
            return files[filename]
        raise FileNotFoundError(filename)

    store.load_file.side_effect = _load_file
    return store


def _make_create_spec(filename: str = "p.md") -> _MemoryUpdateSpec:
    return _MemoryUpdateSpec(
        action="create",
        filename=filename,
        name=filename.removesuffix(".md"),
        description="설명",
        memory_type="feedback",
        body="내용",
    )


class TestGuardConditions:
    @pytest.mark.asyncio
    async def test_low_turn_count_skips(self):
        store = _make_store_with([], {})
        llm = AsyncMock(spec=LLMPort)
        uc = UpdateUserMemoryUseCase(store, llm, turn_count_threshold=3)

        result = await uc.execute(uuid4(), turn_count=2, session_summary="짧은 세션", workflow=_make_workflow())
        assert result is False
        llm.generate_structured.assert_not_called()

    @pytest.mark.asyncio
    async def test_none_workflow_skips(self):
        store = _make_store_with([], {})
        llm = AsyncMock(spec=LLMPort)
        uc = UpdateUserMemoryUseCase(store, llm)

        result = await uc.execute(uuid4(), turn_count=5, session_summary="세션", workflow=None)
        assert result is False
        llm.generate_structured.assert_not_called()

    @pytest.mark.asyncio
    async def test_empty_workflow_nodes_skips(self):
        store = _make_store_with([], {})
        llm = AsyncMock(spec=LLMPort)
        uc = UpdateUserMemoryUseCase(store, llm)

        workflow = _make_workflow(node_count=0)
        result = await uc.execute(uuid4(), turn_count=5, session_summary="세션", workflow=workflow)
        assert result is False
        llm.generate_structured.assert_not_called()

    @pytest.mark.asyncio
    async def test_threshold_boundary_passes(self):
        store = _make_store_with([], {})
        llm = AsyncMock(spec=LLMPort)
        llm.generate_structured.return_value = _make_llm_result([_make_create_spec()])
        uc = UpdateUserMemoryUseCase(store, llm, turn_count_threshold=3)

        result = await uc.execute(uuid4(), turn_count=3, session_summary="세션", workflow=_make_workflow())
        assert result is True


class TestUpdateUserMemoryUseCase:
    @pytest.mark.asyncio
    async def test_creates_new_file_on_create_action(self):
        store = _make_store_with([], {})
        llm = AsyncMock(spec=LLMPort)
        llm.generate_structured.return_value = _make_llm_result([
            _MemoryUpdateSpec(
                action="create",
                filename="workflow_patterns.md",
                name="workflow-patterns",
                description="워크플로우 패턴",
                memory_type="feedback",
                body="슬랙 알림 선호",
            )
        ])
        uc = UpdateUserMemoryUseCase(store, llm)
        saved = await uc.execute(uuid4(), turn_count=5, session_summary="슬랙 워크플로우 완료", workflow=_make_workflow())
        assert saved is True
        store.save_file.assert_called_once()
        store.save_index.assert_called_once()

    @pytest.mark.asyncio
    async def test_skip_action_does_not_save(self):
        store = _make_store_with([], {})
        llm = AsyncMock(spec=LLMPort)
        llm.generate_structured.return_value = _make_llm_result([
            _MemoryUpdateSpec(action="skip", filename="x.md", name="x", description="", memory_type="project", body="")
        ])
        uc = UpdateUserMemoryUseCase(store, llm)
        saved = await uc.execute(uuid4(), turn_count=5, session_summary="세션", workflow=_make_workflow())
        assert saved is False
        store.save_file.assert_not_called()

    @pytest.mark.asyncio
    async def test_none_session_summary_allowed(self):
        store = _make_store_with([], {})
        llm = AsyncMock(spec=LLMPort)
        llm.generate_structured.return_value = _make_llm_result([_make_create_spec()])
        uc = UpdateUserMemoryUseCase(store, llm)

        result = await uc.execute(uuid4(), turn_count=5, session_summary=None, workflow=_make_workflow())
        assert result is True

    @pytest.mark.asyncio
    async def test_debounce_blocks_second_call(self):
        store = _make_store_with([], {})
        llm = AsyncMock(spec=LLMPort)
        llm.generate_structured.return_value = _make_llm_result([_make_create_spec()])
        uc = UpdateUserMemoryUseCase(store, llm, debounce_window=timedelta(hours=1))
        uid = uuid4()

        first = await uc.execute(uid, turn_count=5, session_summary="첫 세션", workflow=_make_workflow())
        second = await uc.execute(uid, turn_count=5, session_summary="두 번째 세션", workflow=_make_workflow())
        assert first is True
        assert second is False
        assert llm.generate_structured.call_count == 1

    @pytest.mark.asyncio
    async def test_debounce_allows_call_after_window(self):
        store = _make_store_with([], {})
        llm = AsyncMock(spec=LLMPort)
        llm.generate_structured.return_value = _make_llm_result([_make_create_spec()])
        uc = UpdateUserMemoryUseCase(store, llm, debounce_window=timedelta(minutes=0))
        uid = uuid4()

        first = await uc.execute(uid, turn_count=5, session_summary="첫 세션", workflow=_make_workflow())
        second = await uc.execute(uid, turn_count=5, session_summary="두 번째 세션", workflow=_make_workflow())
        assert first is True
        assert second is True
        assert llm.generate_structured.call_count == 2

    @pytest.mark.asyncio
    async def test_existing_index_entries_preserved_on_new_file(self):
        existing_ref = MemoryFileRef(filename="old.md", name="old", description="기존")
        existing_file = MemoryFile(filename="old.md", name="old", description="기존", memory_type="user", body="기존 내용")
        store = _make_store_with([existing_ref], {"old.md": existing_file})
        llm = AsyncMock(spec=LLMPort)
        llm.generate_structured.return_value = _make_llm_result([
            _MemoryUpdateSpec(action="create", filename="new.md", name="new", description="신규", memory_type="feedback", body="신규 내용")
        ])
        uc = UpdateUserMemoryUseCase(store, llm)
        await uc.execute(uuid4(), turn_count=5, session_summary="신규 패턴", workflow=_make_workflow())

        saved_refs = store.save_index.call_args[0][1]
        filenames = {r.filename for r in saved_refs}
        assert "old.md" in filenames
        assert "new.md" in filenames
