"""validator_node 단위 테스트 — 구조 검증 통과/실패 + PipelineStatusFrame emit."""
from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from common_schemas.agent import DraftSpec, SlotFillingState
from common_schemas.transport import PipelineStatusFrame, RationaleDeltaFrame
from common_schemas.workflow import NodeConfig, WorkflowSchema
from common_schemas.enums import RiskLevel

from ai_agent.adapters.langgraph.composer_graph import LangGraphOrchestrator
from ai_agent.domain.ports.node_registry import NodeRegistry
from ai_agent.domain.ports.workflow_repository import WorkflowRepository
from ai_agent.domain.services import (
    DrafterService,
    IntentAnalyzerService,
    QAEvaluatorService,
    SlotFillingService,
)


def _build_orchestrator(validator=None) -> LangGraphOrchestrator:
    from nodes_graph.domain.services.graph_validator import GraphValidator

    return LangGraphOrchestrator(
        intent_analyzer=AsyncMock(spec=IntentAnalyzerService),
        drafter=AsyncMock(spec=DrafterService),
        qa_evaluator=AsyncMock(spec=QAEvaluatorService),
        slot_filler=SlotFillingService(),
        node_registry=AsyncMock(spec=NodeRegistry),
        workflow_repo=AsyncMock(spec=WorkflowRepository),
        graph_validator=validator or AsyncMock(spec=GraphValidator),
    )


def _empty_workflow() -> WorkflowSchema:
    return WorkflowSchema(
        workflow_id=uuid4(),
        name="Test",
        scope="private",
        is_draft=True,
        nodes=[],
        connections=[],
        owner_user_id=uuid4(),
    )


def _make_state(workflow=None) -> dict:
    return {
        "session_id": uuid4(),
        "user_id": uuid4(),
        "user_role": "User",
        "department_id": None,
        "messages": [{"role": "user", "content": "테스트"}],
        "turn_count": 1,
        "personal_memory": [],
        "intent": "draft",
        "intent_analyzed_entities": {},
        "draft_spec": DraftSpec(
            natural_language_intent="테스트",
            unresolved_nodes=[],
            discovered_entities={},
            slot_filling_state=SlotFillingState(asked=[], pending=[], filled={}),
            consultant_turn_count=0,
        ),
        "node_candidates": [],
        "workflow_draft": workflow if workflow is not None else _empty_workflow(),
        "qa_attempts": 0,
        "qa_score": 0.0,
        "pass_flag": False,
        "qa_feedback": "",
        "collected_frames": [],
        "error": None,
    }


class TestValidatorNodePass:
    @pytest.mark.asyncio
    async def test_pass_flag_true_on_valid_workflow(self):
        from nodes_graph.domain.services.graph_validator import GraphValidator
        validator = AsyncMock(spec=GraphValidator)
        validator.validate = AsyncMock(return_value=None)
        oc = _build_orchestrator(validator=validator)
        result = await oc._validator_node(_make_state())
        assert result["pass_flag"] is True
        assert result["validation_issues"] is None

    @pytest.mark.asyncio
    async def test_emits_rationale_delta_frame(self):
        from nodes_graph.domain.services.graph_validator import GraphValidator
        validator = AsyncMock(spec=GraphValidator)
        validator.validate = AsyncMock(return_value=None)
        oc = _build_orchestrator(validator=validator)
        result = await oc._validator_node(_make_state())
        frames = [f for f in result.get("collected_frames", []) if isinstance(f, RationaleDeltaFrame)]
        assert len(frames) == 1
        assert "검증 통과" in frames[0].delta

    @pytest.mark.asyncio
    async def test_emits_pipeline_status_frame(self):
        from nodes_graph.domain.services.graph_validator import GraphValidator
        validator = AsyncMock(spec=GraphValidator)
        validator.validate = AsyncMock(return_value=None)
        oc = _build_orchestrator(validator=validator)
        result = await oc._validator_node(_make_state())
        frames = [f for f in result.get("collected_frames", []) if isinstance(f, PipelineStatusFrame)]
        assert len(frames) == 1
        assert frames[0].service_name == "validator"
        assert frames[0].status == "completed"
        assert frames[0].elapsed_ms >= 0

    @pytest.mark.asyncio
    async def test_elapsed_ms_not_hardcoded_zero(self):
        """elapsed_ms가 항상 0이 아닌 실측값임을 확인."""
        import asyncio
        from nodes_graph.domain.services.graph_validator import GraphValidator

        async def slow_validate(workflow):
            await asyncio.sleep(0.01)

        validator = AsyncMock(spec=GraphValidator)
        validator.validate = slow_validate
        oc = _build_orchestrator(validator=validator)
        result = await oc._validator_node(_make_state())
        frames = [f for f in result.get("collected_frames", []) if isinstance(f, PipelineStatusFrame)]
        assert frames[0].elapsed_ms > 0


class TestValidatorNodeFail:
    @pytest.mark.asyncio
    async def test_pass_flag_false_on_invalid_workflow(self):
        from nodes_graph.domain.services.graph_validator import GraphValidator
        validator = AsyncMock(spec=GraphValidator)
        validator.validate = AsyncMock(side_effect=Exception("사이클 감지"))
        oc = _build_orchestrator(validator=validator)
        result = await oc._validator_node(_make_state())
        assert result["pass_flag"] is False
        assert "사이클 감지" in result["validation_issues"]

    @pytest.mark.asyncio
    async def test_no_frames_on_failure(self):
        """검증 실패 시 프레임 없이 pass_flag/validation_issues만 반환."""
        from nodes_graph.domain.services.graph_validator import GraphValidator
        validator = AsyncMock(spec=GraphValidator)
        validator.validate = AsyncMock(side_effect=Exception("고립 노드 존재"))
        oc = _build_orchestrator(validator=validator)
        result = await oc._validator_node(_make_state())
        assert result.get("collected_frames") is None or result.get("collected_frames") == []

    @pytest.mark.asyncio
    async def test_no_workflow_returns_empty(self):
        """workflow_draft가 None이면 빈 dict 반환."""
        oc = _build_orchestrator()
        state = _make_state()
        state["workflow_draft"] = None
        result = await oc._validator_node(state)
        assert result == {}
