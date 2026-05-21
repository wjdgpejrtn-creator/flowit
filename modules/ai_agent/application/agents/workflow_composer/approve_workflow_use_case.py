"""ApproveWorkflowUseCase — 사용자 승인 이벤트 처리.

흐름:
  1. WorkflowDraftStore에서 AI 초안(draft) 로드
  2. WorkflowRepository에서 최종 워크플로우(final) 로드
  3. WorkflowDiffService.compute(draft, final) → WorkflowDiff
  4. WorkflowDiff를 Personalization Agent에 이벤트로 전달
  5. WorkflowDraftStore에서 draft 삭제 (정리)

spec §3.3 사용자 승인 diff 흐름 참조.
"""
from __future__ import annotations

import logging
from uuid import UUID

from common_schemas.agent import MemoryEntry
from common_schemas.agent_protocol import AgentProtocolRequest, AgentProtocolResponse
from common_schemas.agent import AgentState
from common_schemas.enums import AgentMode, ExecutionStatus

from ....domain.ports.sub_agent_client import SubAgentClient
from ....domain.ports.workflow_draft_store import WorkflowDraftStore
from ....domain.ports.workflow_repository import WorkflowRepository
from ....domain.services.workflow_diff_service import WorkflowDiff, WorkflowDiffService

_logger = logging.getLogger(__name__)


class ApproveWorkflowUseCase:
    """사용자가 워크플로우를 최종 승인했을 때 diff를 계산하고 Personalization에 전달.

    Draft(AI 제안) vs Final(사용자 확정) 비교 결과를 피드백 메모리로 변환하는 것은
    Personalization Agent(햄햄 담당)의 책임이다. 이 UseCase는 diff를 계산하고
    이벤트만 전달한다.
    """

    def __init__(
        self,
        workflow_draft_store: WorkflowDraftStore,
        workflow_repo: WorkflowRepository,
        diff_service: WorkflowDiffService,
        personalization_client: SubAgentClient | None = None,
    ) -> None:
        self._draft_store = workflow_draft_store
        self._workflow_repo = workflow_repo
        self._diff_service = diff_service
        self._personalization = personalization_client

    async def execute(
        self,
        session_id: UUID,
        user_id: UUID,
        workflow_id: UUID,
    ) -> WorkflowDiff | None:
        """승인 처리 후 WorkflowDiff를 반환한다. draft가 없으면 None."""
        draft = await self._draft_store.load_draft(session_id)
        if draft is None:
            _logger.info("approve: session %s의 draft 없음 — diff 계산 스킵", session_id)
            return None

        final = await self._workflow_repo.find_by_id(workflow_id)
        if final is None:
            _logger.warning("approve: workflow_id=%s 없음 — diff 계산 스킵", workflow_id)
            await self._draft_store.delete_draft(session_id)
            return None

        diff = self._diff_service.compute(draft, final)

        if not diff.is_empty() and self._personalization is not None:
            await self._notify_personalization(session_id, user_id, diff)

        await self._draft_store.delete_draft(session_id)
        return diff

    async def _notify_personalization(
        self,
        session_id: UUID,
        user_id: UUID,
        diff: WorkflowDiff,
    ) -> None:
        """WorkflowDiff를 Personalization Agent에 이벤트로 전달."""
        feedback_lines = diff.to_feedback_lines()
        stub_state = AgentState(
            session_id=session_id,
            user_id=user_id,
            messages=[],
            turn_count=0,
            mode=AgentMode.GENERAL,
            execution_status=ExecutionStatus.RUNNING,
        )
        req = AgentProtocolRequest(
            session_id=session_id,
            user_id=user_id,
            state=stub_state,
            payload={
                "action": "workflow_diff_feedback",
                "feedback_lines": feedback_lines,
                "diff_summary": {
                    "added_nodes": len(diff.added_nodes),
                    "removed_nodes": len(diff.removed_nodes),
                    "modified_params": len(diff.modified_params),
                },
            },
        )
        try:
            async for resp in self._personalization.send(req):
                if resp.next_action != "continue":
                    break
        except Exception as exc:
            _logger.warning("Personalization diff 이벤트 전달 실패 (non-fatal): %s", exc)
