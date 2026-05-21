"""InMemoryWorkflowDraftStore 단위 테스트."""
from __future__ import annotations

from uuid import uuid4

import pytest

from common_schemas import WorkflowSchema

from ai_agent.adapters.memory.in_memory_draft_store import InMemoryWorkflowDraftStore


def _make_workflow() -> WorkflowSchema:
    return WorkflowSchema(
        workflow_id=uuid4(),
        name="test",
        scope="private",
        is_draft=True,
        nodes=[],
        connections=[],
    )


class TestInMemoryWorkflowDraftStore:
    def setup_method(self):
        self.store = InMemoryWorkflowDraftStore()

    @pytest.mark.asyncio
    async def test_save_and_load(self):
        session_id = uuid4()
        wf = _make_workflow()
        await self.store.save_draft(session_id, wf)
        loaded = await self.store.load_draft(session_id)
        assert loaded is not None
        assert loaded.workflow_id == wf.workflow_id

    @pytest.mark.asyncio
    async def test_load_missing_returns_none(self):
        result = await self.store.load_draft(uuid4())
        assert result is None

    @pytest.mark.asyncio
    async def test_save_overwrites_existing(self):
        session_id = uuid4()
        wf1 = _make_workflow()
        wf2 = _make_workflow()
        await self.store.save_draft(session_id, wf1)
        await self.store.save_draft(session_id, wf2)
        loaded = await self.store.load_draft(session_id)
        assert loaded.workflow_id == wf2.workflow_id

    @pytest.mark.asyncio
    async def test_delete_removes_draft(self):
        session_id = uuid4()
        await self.store.save_draft(session_id, _make_workflow())
        await self.store.delete_draft(session_id)
        assert await self.store.load_draft(session_id) is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent_does_not_raise(self):
        await self.store.delete_draft(uuid4())  # 예외 없어야 함

    @pytest.mark.asyncio
    async def test_multiple_sessions_isolated(self):
        s1, s2 = uuid4(), uuid4()
        wf1, wf2 = _make_workflow(), _make_workflow()
        await self.store.save_draft(s1, wf1)
        await self.store.save_draft(s2, wf2)
        assert (await self.store.load_draft(s1)).workflow_id == wf1.workflow_id
        assert (await self.store.load_draft(s2)).workflow_id == wf2.workflow_id
        await self.store.delete_draft(s1)
        assert await self.store.load_draft(s1) is None
        assert (await self.store.load_draft(s2)).workflow_id == wf2.workflow_id
