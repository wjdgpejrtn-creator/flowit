import json
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from common_schemas import WorkflowSchema
from common_schemas.exceptions import ExecutionError

from ai_agent.domain.ports import LLMPort
from ai_agent.domain.services import QAEvaluatorService


def _mock_llm(score: float) -> LLMPort:
    llm = AsyncMock(spec=LLMPort)
    llm.generate.return_value = {
        "content": json.dumps({
            "score": score,
            "pass_flag": score >= 8,
            "reason": "test reason",
            "feedback": "test feedback",
        })
    }
    return llm


def _empty_workflow() -> WorkflowSchema:
    return WorkflowSchema(
        workflow_id=uuid4(),
        name="Test",
        scope="private",
        is_draft=True,
        nodes=[],
        connections=[],
    )


class TestQAEvaluatorService:
    @pytest.mark.asyncio
    async def test_pass_when_score_gte_8(self):
        svc = QAEvaluatorService(_mock_llm(9.0))
        result = await svc.evaluate(_empty_workflow(), [])
        assert result.pass_flag is True
        assert result.score == 9.0

    @pytest.mark.asyncio
    async def test_fail_when_score_lt_8(self):
        svc = QAEvaluatorService(_mock_llm(6.5))
        result = await svc.evaluate(_empty_workflow(), [])
        assert result.pass_flag is False

    @pytest.mark.asyncio
    async def test_boundary_score_8_passes(self):
        svc = QAEvaluatorService(_mock_llm(8.0))
        result = await svc.evaluate(_empty_workflow(), [])
        assert result.pass_flag is True

    @pytest.mark.asyncio
    async def test_parse_error_raises(self):
        llm = AsyncMock(spec=LLMPort)
        llm.generate.return_value = {"content": "invalid json{{"}
        svc = QAEvaluatorService(llm)
        with pytest.raises(ExecutionError) as exc_info:
            await svc.evaluate(_empty_workflow(), [])
        assert exc_info.value.code == "E_QA_PARSE"
