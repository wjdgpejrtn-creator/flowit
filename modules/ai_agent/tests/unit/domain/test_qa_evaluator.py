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
    async def test_score_clamped_below_threshold_when_gated_by_missing(self):
        """점수↔판정 정합 — missing 게이트로 fail시키면서 만점 점수를 노출하면 '10/10 (재시도 필요)'
        모순 표시가 된다(조장 e2e 발견). 게이트 발동 시 점수를 임계(8) 미만으로 낮춰 일치시킨다."""
        svc = QAEvaluatorService(_mock_llm(10.0, missing=["데이터소스 노드"]))
        result = await svc.evaluate(_empty_workflow(), _spec())
        assert result.pass_flag is False
        assert result.score < 8.0  # 점수와 판정이 일치(모순 표시 차단)

    @pytest.mark.asyncio
    async def test_score_not_clamped_when_no_missing(self):
        # missing 없으면 LLM 점수 그대로 노출(정상 통과는 점수 보존).
        svc = QAEvaluatorService(_mock_llm(10.0, missing=[]))
        result = await svc.evaluate(_empty_workflow(), _spec())
        assert result.pass_flag is True
        assert result.score == 10.0

    @pytest.mark.asyncio
    async def test_pass_when_score_high_and_no_missing(self):
        svc = QAEvaluatorService(_mock_llm(9.0, missing=[]))
        result = await svc.evaluate(_empty_workflow(), _spec())
        assert result.pass_flag is True

    @pytest.mark.asyncio
    @pytest.mark.parametrize("sentinel", ["none", "None", "N/A", "없음", "해당 없음", "null", "-", "none."])
    async def test_sentinel_missing_treated_as_empty_passes(self, sentinel):
        """QA LLM이 '누락 없음'을 ['none']/['없음'] 등 센티넬로 반환해도 만점이면 통과해야 한다.

        실제 staging 버그: score=10인데 missing=['none']로 pass_flag=False가 돼 완성 워크플로우가
        동일 draft 무한 재시도→E_QA_EXHAUSTED('누락된 필수 노드/채널: none')로 헛돌았다.
        """
        svc = QAEvaluatorService(_mock_llm(10.0, missing=[sentinel]))
        result = await svc.evaluate(_empty_workflow(), _spec())
        assert result.pass_flag is True
        assert "누락된 필수 노드" not in (result.feedback or "")

    @pytest.mark.asyncio
    async def test_sentinel_mixed_with_real_missing_keeps_real(self):
        """센티넬과 진짜 누락이 섞이면 진짜 누락만 남겨 fail 유지."""
        svc = QAEvaluatorService(_mock_llm(10.0, missing=["none", "Gmail 노드"]))
        result = await svc.evaluate(_empty_workflow(), _spec())
        assert result.pass_flag is False
        assert "Gmail 노드" in result.feedback
        assert "none" not in result.feedback

    @pytest.mark.asyncio
    async def test_parse_error_raises(self):
        llm = AsyncMock(spec=LLMPort)
        llm.generate_structured = AsyncMock(side_effect=Exception("parse error"))
        svc = QAEvaluatorService(llm)
        with pytest.raises(ExecutionError) as exc_info:
            await svc.evaluate(_empty_workflow(), _spec())
        assert exc_info.value.code == "E_QA_PARSE"
