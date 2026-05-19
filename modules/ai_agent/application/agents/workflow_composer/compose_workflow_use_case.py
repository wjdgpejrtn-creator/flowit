from __future__ import annotations

from typing import AsyncGenerator
from uuid import UUID, uuid4

from common_schemas import DraftSpec, SlotFillingState
from common_schemas.transport import (
    AgentNodeFrame,
    DraftSpecDeltaFrame,
    IntentResultFrame,
    QAMetricFrame,
    ResultFrame,
    SessionFrame,
    SlotFillQuestionFrame,
    SSEFrame,
    WorkflowDraftFrame,
)

from ....domain.ports.node_registry import NodeRegistry
from ....domain.ports.workflow_repository import WorkflowRepository
from ....domain.services import DrafterService, IntentAnalyzerService, QAEvaluatorService, SlotFillingService

# 후속 구현에서 사용 — TurnLimit(≤25 강제), QualityThreshold(score≥8 통과) VO는
# 각각 turn_count 검증 / qa_evaluator 통과 판정에 적용 예정. spec §2.1 도메인 VO 참조.
_MAX_QA_RETRY = 3


class ComposeWorkflowUseCase:
    def __init__(
        self,
        intent_analyzer: IntentAnalyzerService,
        drafter: DrafterService,
        qa_evaluator: QAEvaluatorService,
        slot_filler: SlotFillingService,
        node_registry: NodeRegistry,
        workflow_repo: WorkflowRepository,
    ) -> None:
        self._intent_analyzer = intent_analyzer
        self._drafter = drafter
        self._qa_evaluator = qa_evaluator
        self._slot_filler = slot_filler
        self._node_registry = node_registry
        self._workflow_repo = workflow_repo

    async def execute(
        self,
        user_id: UUID,
        session_id: UUID,
        message: str,
    ) -> AsyncGenerator[SSEFrame, None]:
        return self._stream(user_id, session_id, message)

    async def _stream(
        self,
        user_id: UUID,
        session_id: UUID,
        message: str,
    ) -> AsyncGenerator[SSEFrame, None]:
        yield SessionFrame(session_id=session_id, langgraph_thread_id=uuid4())

        # 1. Intent analysis
        yield AgentNodeFrame(agent_node_name="intent_node")
        messages = [{"role": "user", "content": message}]
        intent = await self._intent_analyzer.analyze(messages, context={})
        yield IntentResultFrame(intent=intent.intent, entities=intent.analyzed_entities)

        # 2. Clarify: slot filling
        if intent.intent == "clarify":
            draft_spec = DraftSpec(
                natural_language_intent=message,
                unresolved_nodes=[],
                discovered_entities=intent.analyzed_entities,
                slot_filling_state=SlotFillingState(asked=[], pending=list(intent.analyzed_entities.keys()), filled={}),
                consultant_turn_count=0,
            )
            question = self._slot_filler.next_question(draft_spec.slot_filling_state, draft_spec)
            if question:
                yield SlotFillQuestionFrame(question=question, field_name="unknown")
            return

        # 3. Retrieve candidate nodes
        yield AgentNodeFrame(agent_node_name="retriever_node")
        candidates = await self._node_registry.search(message)

        # 4. Build DraftSpec
        draft_spec = DraftSpec(
            natural_language_intent=message,
            unresolved_nodes=[],
            discovered_entities=intent.analyzed_entities,
            slot_filling_state=SlotFillingState(asked=[], pending=[], filled={}),
            consultant_turn_count=0,
        )

        # 5. Draft + QA loop (max 3 retries)
        workflow = None
        for attempt in range(_MAX_QA_RETRY):
            yield AgentNodeFrame(agent_node_name="drafter_node")
            yield DraftSpecDeltaFrame(delta={"attempt": attempt + 1})
            workflow = await self._drafter.draft(draft_spec, candidates)
            nodes_data = [n.model_dump(mode="json") for n in workflow.nodes]
            connections_data = [c.model_dump(mode="json") for c in workflow.connections]
            yield WorkflowDraftFrame(nodes=nodes_data, connections=connections_data)

            yield AgentNodeFrame(agent_node_name="qa_evaluator_node")
            qa_result = await self._qa_evaluator.evaluate(workflow, draft_spec)
            yield QAMetricFrame(
                score=qa_result.score,
                attempt=attempt + 1,
                pass_flag=qa_result.pass_flag,
                feedback=qa_result.feedback,
            )
            if qa_result.pass_flag:
                break

        # 6. Promote and save
        yield AgentNodeFrame(agent_node_name="promote_node")
        workflow_id = await self._workflow_repo.save(workflow)

        yield ResultFrame(intent="draft", payload={"workflow_id": str(workflow_id)})
