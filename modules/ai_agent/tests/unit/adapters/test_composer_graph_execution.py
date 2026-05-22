"""execute_node / evaluate_output_node / user_confirm_node 단위 테스트."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from common_schemas.transport import PipelineStatusFrame, ResultFrame

from ai_agent.adapters.langgraph.composer_graph import LangGraphOrchestrator
from ai_agent.domain.ports.node_registry import NodeRegistry
from ai_agent.domain.ports.workflow_repository import WorkflowRepository
from ai_agent.domain.services import (
    DrafterService,
    IntentAnalyzerService,
    QAEvaluatorService,
    SlotFillingService,
)


def _build_orchestrator(
    execution_engine_url: str = "",
    llm=None,
) -> LangGraphOrchestrator:
    from nodes_graph.domain.services.graph_validator import GraphValidator

    return LangGraphOrchestrator(
        intent_analyzer=AsyncMock(spec=IntentAnalyzerService),
        drafter=AsyncMock(spec=DrafterService),
        qa_evaluator=AsyncMock(spec=QAEvaluatorService),
        slot_filler=SlotFillingService(),
        node_registry=AsyncMock(spec=NodeRegistry),
        workflow_repo=AsyncMock(spec=WorkflowRepository),
        graph_validator=AsyncMock(spec=GraphValidator),
        llm=llm,
        execution_engine_url=execution_engine_url,
    )


def _make_state(**overrides) -> dict:
    base = {
        "session_id": uuid4(),
        "user_id": uuid4(),
        "user_role": "User",
        "department_id": None,
        "messages": [{"role": "user", "content": "테스트"}],
        "turn_count": 1,
        "personal_memory": [],
        "intent": None,
        "intent_analyzed_entities": {},
        "draft_spec": None,
        "node_candidates": [],
        "workflow_draft": None,
        "qa_attempts": 0,
        "qa_score": 0.0,
        "pass_flag": False,
        "qa_feedback": "",
        "collected_frames": [],
        "error": None,
        "saved_workflow_id": None,
        "execution_id": None,
        "execution_result": None,
        "output_quality_score": 0.0,
        "output_quality_feedback": "",
    }
    base.update(overrides)
    return base


# ──────────────────────────────────────────────────────────────────────────────
# execute_node
# ──────────────────────────────────────────────────────────────────────────────


class TestExecuteNode:
    @pytest.mark.asyncio
    async def test_skips_when_no_workflow_id(self):
        """saved_workflow_id 없으면 skipped 상태로 반환."""
        oc = _build_orchestrator(execution_engine_url="http://engine")
        result = await oc._execute_node(_make_state(saved_workflow_id=None))
        assert result["execution_result"]["status"] == "skipped"
        assert result["execution_id"] is None

    @pytest.mark.asyncio
    async def test_skips_when_no_engine_url(self):
        """EXECUTION_ENGINE_URL 미설정 시 skipped 상태로 반환."""
        oc = _build_orchestrator(execution_engine_url="")
        result = await oc._execute_node(_make_state(saved_workflow_id=uuid4()))
        assert result["execution_result"]["status"] == "skipped"
        assert "EXECUTION_ENGINE_URL" in result["execution_result"]["reason"]

    @pytest.mark.asyncio
    async def test_returns_failed_on_http_error(self):
        """실행 엔진 HTTP 오류 시 failed 상태로 반환."""
        oc = _build_orchestrator(execution_engine_url="http://engine")
        state = _make_state(saved_workflow_id=uuid4())

        with patch("httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value.__aenter__.return_value = mock_client
            mock_client.post.side_effect = Exception("connection refused")

            result = await oc._execute_node(state)

        assert result["execution_result"]["status"] == "failed"
        assert result["execution_id"] is None
        frames = [f for f in result["collected_frames"] if isinstance(f, PipelineStatusFrame)]
        assert frames[0].status == "failed"

    @pytest.mark.asyncio
    async def test_returns_execution_id_on_success(self):
        """정상 실행 시 execution_id가 state에 저장된다."""
        oc = _build_orchestrator(execution_engine_url="http://engine")
        state = _make_state(saved_workflow_id=uuid4())
        exec_id = "exec-abc-123"

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"execution_id": exec_id}
        mock_resp.raise_for_status = MagicMock()
        poll_result = {"status": "completed", "result": {}}

        with patch("httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value.__aenter__.return_value = mock_client
            mock_client.post.return_value = mock_resp

            with patch.object(oc, "_poll_execution_result", new=AsyncMock(return_value=poll_result)):
                result = await oc._execute_node(state)

        assert result["execution_id"] == exec_id
        assert result["execution_result"]["status"] == "completed"
        frames = [f for f in result["collected_frames"] if isinstance(f, PipelineStatusFrame)]
        assert frames[0].status == "completed"

    @pytest.mark.asyncio
    async def test_returns_timeout_result_on_poll_timeout(self):
        """폴링 타임아웃 시 timeout 상태로 반환."""
        oc = _build_orchestrator(execution_engine_url="http://engine")
        state = _make_state(saved_workflow_id=uuid4())

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"execution_id": "exec-xyz"}
        mock_resp.raise_for_status = MagicMock()
        timeout_result = {"status": "timeout", "execution_id": "exec-xyz"}

        with patch("httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value.__aenter__.return_value = mock_client
            mock_client.post.return_value = mock_resp

            with patch.object(oc, "_poll_execution_result", new=AsyncMock(return_value=timeout_result)):
                result = await oc._execute_node(state)

        assert result["execution_result"]["status"] == "timeout"


# ──────────────────────────────────────────────────────────────────────────────
# evaluate_output_node
# ──────────────────────────────────────────────────────────────────────────────


class TestEvaluateOutputNode:
    @pytest.mark.asyncio
    async def test_failed_status_returns_zero_score(self):
        """실행 결과 failed → score 0.0, frame status failed."""
        oc = _build_orchestrator()
        result = await oc._evaluate_output_node(_make_state(execution_result={"status": "failed"}))
        assert result["output_quality_score"] == 0.0
        frames = [f for f in result["collected_frames"] if isinstance(f, PipelineStatusFrame)]
        assert frames[0].status == "failed"

    @pytest.mark.asyncio
    async def test_timeout_status_returns_zero_score(self):
        """실행 결과 timeout → score 0.0."""
        oc = _build_orchestrator()
        result = await oc._evaluate_output_node(_make_state(execution_result={"status": "timeout"}))
        assert result["output_quality_score"] == 0.0

    @pytest.mark.asyncio
    async def test_cancelled_status_returns_zero_score(self):
        """실행 결과 cancelled → score 0.0."""
        oc = _build_orchestrator()
        result = await oc._evaluate_output_node(_make_state(execution_result={"status": "cancelled"}))
        assert result["output_quality_score"] == 0.0

    @pytest.mark.asyncio
    async def test_skipped_returns_mid_score(self):
        """skipped → score 5.0, frame status completed."""
        oc = _build_orchestrator()
        result = await oc._evaluate_output_node(_make_state(execution_result={"status": "skipped"}))
        assert result["output_quality_score"] == 5.0
        frames = [f for f in result["collected_frames"] if isinstance(f, PipelineStatusFrame)]
        assert frames[0].status == "completed"

    @pytest.mark.asyncio
    async def test_completed_without_llm_returns_default_score(self):
        """LLM 미주입 + completed → 기본값 7.0."""
        oc = _build_orchestrator(llm=None)
        result = await oc._evaluate_output_node(_make_state(execution_result={"status": "completed"}))
        assert result["output_quality_score"] == 7.0
        frames = [f for f in result["collected_frames"] if isinstance(f, PipelineStatusFrame)]
        assert frames[0].status == "completed"

    @pytest.mark.asyncio
    async def test_completed_with_llm_uses_llm_score(self):
        """LLM 주입 + completed → LLM 반환 점수 사용."""
        mock_llm = AsyncMock()
        mock_llm.generate.return_value = '{"score": 9.0, "feedback": "완벽한 실행"}'
        oc = _build_orchestrator(llm=mock_llm)
        result = await oc._evaluate_output_node(_make_state(execution_result={"status": "completed"}))
        assert result["output_quality_score"] == 9.0
        assert result["output_quality_feedback"] == "완벽한 실행"

    @pytest.mark.asyncio
    async def test_llm_failure_falls_back_to_default(self):
        """LLM 평가 실패 시 기본값 7.0으로 폴백."""
        mock_llm = AsyncMock()
        mock_llm.generate.side_effect = Exception("LLM 오류")
        oc = _build_orchestrator(llm=mock_llm)
        result = await oc._evaluate_output_node(_make_state(execution_result={"status": "completed"}))
        assert result["output_quality_score"] == 7.0

    @pytest.mark.asyncio
    async def test_none_execution_result_treated_as_completed(self):
        """execution_result=None → status 'unknown' → 기본값 7.0."""
        oc = _build_orchestrator(llm=None)
        result = await oc._evaluate_output_node(_make_state(execution_result=None))
        assert result["output_quality_score"] == 7.0


# ──────────────────────────────────────────────────────────────────────────────
# user_confirm_node
# ──────────────────────────────────────────────────────────────────────────────


class TestUserConfirmNode:
    @pytest.mark.asyncio
    async def test_emits_result_frame_with_execution_review_intent(self):
        """ResultFrame이 intent='execution_review'로 emit된다."""
        oc = _build_orchestrator()
        state = _make_state(
            saved_workflow_id=uuid4(),
            execution_id="exec-001",
            execution_result={"status": "completed"},
            output_quality_score=8.5,
            output_quality_feedback="훌륭한 실행",
        )
        result = await oc._user_confirm_node(state)
        frames = [f for f in result["collected_frames"] if isinstance(f, ResultFrame)]
        assert len(frames) == 1
        assert frames[0].intent == "execution_review"

    @pytest.mark.asyncio
    async def test_payload_contains_required_fields(self):
        """ResultFrame payload에 필수 필드가 모두 포함된다."""
        wf_id = uuid4()
        oc = _build_orchestrator()
        state = _make_state(
            saved_workflow_id=wf_id,
            execution_id="exec-002",
            execution_result={"status": "completed"},
            output_quality_score=7.0,
            output_quality_feedback="정상 완료",
        )
        result = await oc._user_confirm_node(state)
        payload = result["collected_frames"][0].payload

        assert payload["workflow_id"] == str(wf_id)
        assert payload["execution_id"] == "exec-002"
        assert payload["execution_status"] == "completed"
        assert payload["output_quality_score"] == 7.0
        assert payload["output_quality_feedback"] == "정상 완료"
        assert "session_id" in payload

    @pytest.mark.asyncio
    async def test_none_workflow_id_handled(self):
        """saved_workflow_id=None → payload['workflow_id']가 None."""
        oc = _build_orchestrator()
        state = _make_state(saved_workflow_id=None, execution_result={"status": "skipped"})
        result = await oc._user_confirm_node(state)
        assert result["collected_frames"][0].payload["workflow_id"] is None

    @pytest.mark.asyncio
    async def test_none_execution_id_handled(self):
        """execution_id=None → payload에 None으로 전달."""
        oc = _build_orchestrator()
        state = _make_state(execution_id=None, execution_result={"status": "skipped"})
        result = await oc._user_confirm_node(state)
        assert result["collected_frames"][0].payload["execution_id"] is None

    @pytest.mark.asyncio
    async def test_session_id_in_payload_as_string(self):
        """session_id가 문자열로 payload에 포함된다."""
        session_id = uuid4()
        oc = _build_orchestrator()
        state = _make_state(session_id=session_id)
        result = await oc._user_confirm_node(state)
        assert result["collected_frames"][0].payload["session_id"] == str(session_id)
