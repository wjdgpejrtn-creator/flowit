from __future__ import annotations

import pytest
from datetime import datetime, timedelta, timezone
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


def _make_store_with(refs: list[MemoryFileRef], files: dict[str, MemoryFile], *, claim: bool = True) -> AsyncMock:
    store = AsyncMock(spec=PersonalMemoryStore)
    store.load_index.return_value = refs
    store.claim_debounce_window.return_value = claim

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
    async def test_debounce_blocks_when_claim_fails(self):
        """claim_debounce_window가 False면 LLM 호출 없이 저장 건너뜀."""
        store = _make_store_with([], {}, claim=False)
        llm = AsyncMock(spec=LLMPort)
        uc = UpdateUserMemoryUseCase(store, llm, debounce_window=timedelta(minutes=5))

        result = await uc.execute(uuid4(), turn_count=5, session_summary="세션", workflow=_make_workflow())
        assert result is False
        llm.generate_structured.assert_not_called()

    @pytest.mark.asyncio
    async def test_debounce_allows_call_when_claim_succeeds(self):
        """claim_debounce_window가 True면 LLM 호출 및 저장 진행."""
        store = _make_store_with([], {}, claim=True)
        llm = AsyncMock(spec=LLMPort)
        llm.generate_structured.return_value = _make_llm_result([_make_create_spec()])
        uc = UpdateUserMemoryUseCase(store, llm, debounce_window=timedelta(minutes=5))

        result = await uc.execute(uuid4(), turn_count=5, session_summary="세션", workflow=_make_workflow())
        assert result is True

    @pytest.mark.asyncio
    async def test_first_user_no_debounce(self):
        """신규 유저도 claim 성공 시 저장됨."""
        store = _make_store_with([], {}, claim=True)
        llm = AsyncMock(spec=LLMPort)
        llm.generate_structured.return_value = _make_llm_result([_make_create_spec()])
        uc = UpdateUserMemoryUseCase(store, llm, debounce_window=timedelta(minutes=5))

        result = await uc.execute(uuid4(), turn_count=5, session_summary="첫 세션", workflow=_make_workflow())
        assert result is True

    @pytest.mark.asyncio
    async def test_race_condition_claim_loss_returns_false(self):
        """동시 요청에서 CAS 경쟁 패배 시 LLM 없이 False 반환."""
        store = _make_store_with([], {}, claim=False)
        llm = AsyncMock(spec=LLMPort)
        uc = UpdateUserMemoryUseCase(store, llm)

        result = await uc.execute(uuid4(), turn_count=5, session_summary="세션", workflow=_make_workflow())
        assert result is False
        store.load_index.assert_not_called()
        llm.generate_structured.assert_not_called()

    @pytest.mark.asyncio
    async def test_saved_file_has_updated_at(self):
        """저장된 MemoryFile의 updated_at이 현재 시각으로 설정됨."""
        store = _make_store_with([], {})
        llm = AsyncMock(spec=LLMPort)
        llm.generate_structured.return_value = _make_llm_result([_make_create_spec()])
        uc = UpdateUserMemoryUseCase(store, llm)

        before = datetime.now(timezone.utc)
        await uc.execute(uuid4(), turn_count=5, session_summary="세션", workflow=_make_workflow())
        after = datetime.now(timezone.utc)

        saved_file: MemoryFile = store.save_file.call_args[0][1]
        assert before <= saved_file.updated_at <= after

    @pytest.mark.asyncio
    async def test_existing_index_entries_preserved_on_new_file(self):
        existing_ref = MemoryFileRef(filename="old.md", name="old", description="기존")
        existing_file = MemoryFile(
            filename="old.md",
            name="old",
            description="기존",
            memory_type="user",
            body="기존 내용",
            updated_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
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
