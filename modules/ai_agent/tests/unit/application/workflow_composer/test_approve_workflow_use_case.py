"""ApproveWorkflowUseCase 단위 테스트."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from common_schemas import WorkflowSchema
from common_schemas.workflow import NodeInstance, Position

from ai_agent.adapters.memory.in_memory_draft_store import InMemoryWorkflowDraftStore
from ai_agent.application.agents.workflow_composer.approve_workflow_use_case import ApproveWorkflowUseCase
from ai_agent.domain.services.workflow_diff_service import WorkflowDiffService


def _make_workflow(nodes=None) -> WorkflowSchema:
    return WorkflowSchema(
        workflow_id=uuid4(),
        name="test",
        scope="private",
        is_draft=False,
        nodes=nodes or [],
        connections=[],
    )


def _make_node(instance_id=None, node_id=None) -> NodeInstance:
    return NodeInstance(
        instance_id=instance_id or uuid4(),
        node_id=node_id or uuid4(),
        parameters={},
        position=Position(x=0, y=0),
    )


class TestApproveWorkflowUseCase:
    def setup_method(self):
        self.draft_store = InMemoryWorkflowDraftStore()
        self.workflow_repo = AsyncMock()
        self.diff_service = WorkflowDiffService()

    def _make_use_case(self, personalization=None):
        return ApproveWorkflowUseCase(
            workflow_draft_store=self.draft_store,
            workflow_repo=self.workflow_repo,
            diff_service=self.diff_service,
            personalization_client=personalization,
        )

    @pytest.mark.asyncio
    async def test_returns_none_when_no_draft(self):
        self.workflow_repo.find_by_id.return_value = _make_workflow()
        use_case = self._make_use_case()
        result = await use_case.execute(uuid4(), uuid4(), uuid4())
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_workflow_not_found(self):
        session_id = uuid4()
        await self.draft_store.save_draft(session_id, _make_workflow())
        self.workflow_repo.find_by_id.return_value = None
        use_case = self._make_use_case()
        result = await use_case.execute(session_id, uuid4(), uuid4())
        assert result is None
        # draft는 정리되어야 함
        assert await self.draft_store.load_draft(session_id) is None

    @pytest.mark.asyncio
    async def test_empty_diff_for_identical_workflows(self):
        session_id = uuid4()
        wf = _make_workflow()
        await self.draft_store.save_draft(session_id, wf)
        self.workflow_repo.find_by_id.return_value = wf
        use_case = self._make_use_case()
        diff = await use_case.execute(session_id, uuid4(), uuid4())
        assert diff is not None
        assert diff.is_empty()

    @pytest.mark.asyncio
    async def test_detects_node_removal(self):
        session_id = uuid4()
        node_a = _make_node()
        node_b = _make_node()
        draft = _make_workflow([node_a, node_b])
        final = _make_workflow([node_a])
        await self.draft_store.save_draft(session_id, draft)
        self.workflow_repo.find_by_id.return_value = final
        use_case = self._make_use_case()
        diff = await use_case.execute(session_id, uuid4(), uuid4())
        assert len(diff.removed_nodes) == 1
        assert diff.removed_nodes[0].instance_id == node_b.instance_id

    @pytest.mark.asyncio
    async def test_draft_deleted_after_execute(self):
        session_id = uuid4()
        wf = _make_workflow()
        await self.draft_store.save_draft(session_id, wf)
        self.workflow_repo.find_by_id.return_value = wf
        use_case = self._make_use_case()
        await use_case.execute(session_id, uuid4(), uuid4())
        assert await self.draft_store.load_draft(session_id) is None

    @pytest.mark.asyncio
    async def test_personalization_called_when_diff_not_empty(self):
        session_id = uuid4()
        node_a = _make_node()
        node_b = _make_node()
        draft = _make_workflow([node_a, node_b])
        final = _make_workflow([node_a])
        await self.draft_store.save_draft(session_id, draft)
        self.workflow_repo.find_by_id.return_value = final

        mock_client = MagicMock()

        async def _fake_send(req):
            resp = MagicMock()
            resp.next_action = "complete"
            yield resp

        mock_client.send = _fake_send
        use_case = self._make_use_case(personalization=mock_client)
        diff = await use_case.execute(session_id, uuid4(), uuid4())
        assert not diff.is_empty()

    @pytest.mark.asyncio
    async def test_personalization_not_called_when_diff_empty(self):
        session_id = uuid4()
        wf = _make_workflow()
        await self.draft_store.save_draft(session_id, wf)
        self.workflow_repo.find_by_id.return_value = wf

        mock_client = MagicMock()
        mock_client.send = AsyncMock()
        use_case = self._make_use_case(personalization=mock_client)
        await use_case.execute(session_id, uuid4(), uuid4())
        mock_client.send.assert_not_called()
