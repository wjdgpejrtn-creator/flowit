from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from common_schemas import WorkflowSchema
from common_schemas.transport import ResultFrame, SessionFrame

from ai_agent.application.agents.workflow_composer import ComposeWorkflowUseCase
from ai_agent.domain.ports import NodeRegistry, WorkflowRepository
from ai_agent.domain.services import (
    DrafterService,
    IntentAnalyzerService,
    QAEvaluatorService,
    SlotFillingService,
)


def _mock_intent(intent_type: str = "draft"):
    from common_schemas import IntentResult
    svc = AsyncMock(spec=IntentAnalyzerService)
    svc.analyze = AsyncMock(return_value=IntentResult(
        intent=intent_type, confidence=0.95, analyzed_entities={}
    ))
    return svc


def _mock_drafter():
    svc = AsyncMock(spec=DrafterService)
    svc.draft = AsyncMock(return_value=WorkflowSchema(
        workflow_id=uuid4(), name="Test", scope="private",
        is_draft=True, nodes=[], connections=[], owner_user_id=uuid4(),
    ))
    return svc


def _mock_qa(pass_flag: bool = True):
    from common_schemas import EvaluationResult
    svc = AsyncMock(spec=QAEvaluatorService)
    svc.evaluate = AsyncMock(return_value=EvaluationResult(
        score=9.0 if pass_flag else 5.0,
        pass_flag=pass_flag,
        reason="ok",
        feedback="",
    ))
    return svc


def _build_uc(**overrides):
    defaults = dict(
        intent_analyzer=_mock_intent(),
        drafter=_mock_drafter(),
        qa_evaluator=_mock_qa(),
        slot_filler=SlotFillingService(),
        node_registry=AsyncMock(spec=NodeRegistry),
        workflow_repo=AsyncMock(spec=WorkflowRepository),
    )
    defaults["node_registry"].search = AsyncMock(return_value=[])
    defaults["workflow_repo"].save = AsyncMock(return_value=uuid4())
    defaults.update(overrides)
    return ComposeWorkflowUseCase(**defaults)


class TestComposeWorkflowUseCase:
    @pytest.mark.asyncio
    async def test_yields_sse_frames(self):
        uc = _build_uc()
        gen = await uc.execute(uuid4(), uuid4(), "슬랙으로 보고서 보내줘")
        frames = [f async for f in gen]
        assert any(isinstance(f, SessionFrame) for f in frames)
        assert any(isinstance(f, ResultFrame) for f in frames)

    @pytest.mark.asyncio
    async def test_clarify_yields_slot_question(self):
        from common_schemas.transport import SlotFillQuestionFrame
        from common_schemas import IntentResult
        intent_svc = AsyncMock(spec=IntentAnalyzerService)
        intent_svc.analyze = AsyncMock(return_value=IntentResult(
            intent="clarify", confidence=0.9,
            analyzed_entities={"tool": None},
        ))
        uc = _build_uc(intent_analyzer=intent_svc)
        gen = await uc.execute(uuid4(), uuid4(), "자동화 해줘")
        frames = [f async for f in gen]
        assert any(isinstance(f, SlotFillQuestionFrame) for f in frames)

    @pytest.mark.asyncio
    async def test_result_frame_contains_workflow_id(self):
        wf_id = uuid4()
        repo = AsyncMock(spec=WorkflowRepository)
        repo.save = AsyncMock(return_value=wf_id)
        uc = _build_uc(workflow_repo=repo)
        gen = await uc.execute(uuid4(), uuid4(), "보고서 자동화")
        frames = [f async for f in gen]
        result = next(f for f in frames if isinstance(f, ResultFrame))
        assert result.payload["workflow_id"] == str(wf_id)

    @pytest.mark.asyncio
    async def test_qa_retry_on_fail(self):
        from common_schemas import EvaluationResult
        qa = AsyncMock(spec=QAEvaluatorService)
        qa.evaluate = AsyncMock(side_effect=[
            EvaluationResult(score=5.0, pass_flag=False, reason="", feedback=""),
            EvaluationResult(score=5.0, pass_flag=False, reason="", feedback=""),
            EvaluationResult(score=9.0, pass_flag=True, reason="", feedback=""),
        ])
        drafter = _mock_drafter()
        uc = _build_uc(qa_evaluator=qa, drafter=drafter)
        gen = await uc.execute(uuid4(), uuid4(), "보고서 자동화")
        frames = [f async for f in gen]
        assert drafter.draft.call_count == 3
