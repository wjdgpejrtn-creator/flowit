from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from common_schemas import DraftSpec, SlotFillingState, WorkflowSchema
from common_schemas.exceptions import ExecutionError

from ai_agent.domain.ports import LLMPort
from ai_agent.domain.services import QAEvaluatorService


def _mock_llm(score: float, missing: list[str] | None = None) -> LLMPort:
    llm = AsyncMock(spec=LLMPort)
    llm.generate_structured = AsyncMock(return_value=SimpleNamespace(
        score=score,
        reason="test reason",
        feedback="test feedback",
        missing_capabilities=missing or [],
    ))
    return llm


def _empty_workflow() -> WorkflowSchema:
    return WorkflowSchema(
        workflow_id=uuid4(), name="Test", scope="private",
        is_draft=True, nodes=[], connections=[], owner_user_id=uuid4(),
    )


def _spec() -> DraftSpec:
    return DraftSpec(
        natural_language_intent="슬랙으로 보고서 보내줘",
        unresolved_nodes=[],
        discovered_entities={},
        slot_filling_state=SlotFillingState(asked=[], pending=[], filled={}),
        consultant_turn_count=0,
    )


class TestQAEvaluatorService:
    @pytest.mark.asyncio
    async def test_pass_when_score_gte_8(self):
        svc = QAEvaluatorService(_mock_llm(9.0))
        result = await svc.evaluate(_empty_workflow(), _spec())
        assert result.pass_flag is True

    @pytest.mark.asyncio
    async def test_fail_when_score_lt_8(self):
        svc = QAEvaluatorService(_mock_llm(6.5))
        result = await svc.evaluate(_empty_workflow(), _spec())
        assert result.pass_flag is False

    @pytest.mark.asyncio
    async def test_boundary_score_8_passes(self):
        svc = QAEvaluatorService(_mock_llm(8.0))
        result = await svc.evaluate(_empty_workflow(), _spec())
        assert result.pass_flag is True

    @pytest.mark.asyncio
    async def test_high_score_but_missing_capabilities_fails(self):
        """만점이어도 missing_capabilities 비어있지 않으면 fail (#378 자기모순 차단)."""
        svc = QAEvaluatorService(_mock_llm(10.0, missing=["Gmail 노드", "Slack 노드"]))
        result = await svc.evaluate(_empty_workflow(), _spec())
        assert result.pass_flag is False
        assert "Gmail 노드" in result.feedback  # retry가 교정하도록 feedback에 노출

    @pytest.mark.asyncio
    async def test_pass_when_score_high_and_no_missing(self):
        svc = QAEvaluatorService(_mock_llm(9.0, missing=[]))
        result = await svc.evaluate(_empty_workflow(), _spec())
        assert result.pass_flag is True

    @pytest.mark.asyncio
    async def test_parse_error_raises(self):
        llm = AsyncMock(spec=LLMPort)
        llm.generate_structured = AsyncMock(side_effect=Exception("parse error"))
        svc = QAEvaluatorService(llm)
        with pytest.raises(ExecutionError) as exc_info:
            await svc.evaluate(_empty_workflow(), _spec())
        assert exc_info.value.code == "E_QA_PARSE"
