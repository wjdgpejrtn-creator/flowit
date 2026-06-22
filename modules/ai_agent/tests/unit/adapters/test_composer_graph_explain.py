"""_explain_node 단위 테스트 — WorkflowExplanation 생성 + ResultFrame explanation 포함."""
from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from common_schemas.agent import DraftSpec, SlotFillingState
from common_schemas.enums import RiskLevel
from common_schemas.transport import PipelineStatusFrame, ResultFrame
from common_schemas.workflow import Edge, NodeConfig, NodeInstance, Position, WorkflowSchema
from common_schemas.workflow_explanation import WorkflowExplanation

from ai_agent.adapters.langgraph.composer_graph import LangGraphOrchestrator
from ai_agent.domain.ports.node_registry import NodeRegistry
from ai_agent.domain.ports.workflow_repository import WorkflowRepository
from ai_agent.domain.services import (
    DrafterService,
    IntentAnalyzerService,
    QAEvaluatorService,
    SlotFillingService,
)


# ------------------------------------------------------------------ helpers


def _build_orchestrator() -> LangGraphOrchestrator:
    from nodes_graph.domain.services.graph_validator import GraphValidator

    return LangGraphOrchestrator(
        intent_analyzer=AsyncMock(spec=IntentAnalyzerService),
        drafter=AsyncMock(spec=DrafterService),
        qa_evaluator=AsyncMock(spec=QAEvaluatorService),
        slot_filler=SlotFillingService(),
        node_registry=AsyncMock(spec=NodeRegistry),
        workflow_repo=AsyncMock(spec=WorkflowRepository),
        graph_validator=AsyncMock(spec=GraphValidator),
    )


def _make_node_config(name: str = "SlackNode", required_connections: list[str] | None = None) -> NodeConfig:
    return NodeConfig(
        node_id=uuid4(),
        node_type="slack_send",
        name=name,
        category="external",
        version="1.0",
        input_schema={},
        output_schema={},
        parameter_schema={},
        risk_level=RiskLevel.LOW,
        required_connections=required_connections or ["slack"],
        description=f"{name} 설명",
        is_mvp=True,
    )


def _make_instance(node_id, parameters: dict | None = None) -> NodeInstance:
    return NodeInstance(
        instance_id=uuid4(),
        node_id=node_id,
        parameters=parameters or {"channel": "#general"},
        position=Position(x=0.0, y=0.0),
    )


def _make_workflow(nodes: list[NodeInstance], connections: list[Edge] | None = None) -> WorkflowSchema:
    return WorkflowSchema(
        workflow_id=uuid4(),
        name="Test",
        scope="private",
        is_draft=False,
        nodes=nodes,
        connections=connections or [],
        owner_user_id=uuid4(),
    )


def _make_spec(intent: str = "슬랙 알림 전송") -> DraftSpec:
    return DraftSpec(
        natural_language_intent=intent,
        unresolved_nodes=[],
        discovered_entities={},
        slot_filling_state=SlotFillingState(asked=[], pending=[], filled={}),
        consultant_turn_count=0,
    )


def _make_state(workflow=None, spec=None, node_candidates=None) -> dict:
    cfg = _make_node_config()
    inst = _make_instance(cfg.node_id)
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
        "draft_spec": spec or _make_spec(),
        "node_candidates": node_candidates if node_candidates is not None else [cfg],
        "workflow_draft": workflow if workflow is not None else _make_workflow([inst]),
        "qa_attempts": 0,
        "qa_score": 0.0,
        "pass_flag": False,
        "qa_feedback": "",
        "collected_frames": [],
        "error": None,
        "workflow_explanation": None,
        "saved_workflow_id": uuid4(),
    }


# ------------------------------------------------------------------ _explain_node tests


class TestExplainNode:
    @pytest.mark.asyncio
    async def test_returns_workflow_explanation(self):
        oc = _build_orchestrator()
        result = await oc._explain_node(_make_state())
        assert isinstance(result.get("workflow_explanation"), WorkflowExplanation)

    @pytest.mark.asyncio
    async def test_emits_pipeline_status_frame(self):
        oc = _build_orchestrator()
        result = await oc._explain_node(_make_state())
        frames = [f for f in result.get("collected_frames", []) if isinstance(f, PipelineStatusFrame)]
        assert len(frames) == 1
        assert frames[0].service_name == "explain"
        assert frames[0].status == "completed"

    @pytest.mark.asyncio
    async def test_elapsed_ms_non_negative(self):
        oc = _build_orchestrator()
        result = await oc._explain_node(_make_state())
        frames = [f for f in result.get("collected_frames", []) if isinstance(f, PipelineStatusFrame)]
        assert frames[0].elapsed_ms >= 0

    @pytest.mark.asyncio
    async def test_no_workflow_returns_empty(self):
        oc = _build_orchestrator()
        state = _make_state()
        state["workflow_draft"] = None
        result = await oc._explain_node(state)
        assert result == {}

    @pytest.mark.asyncio
    async def test_no_spec_returns_empty(self):
        oc = _build_orchestrator()
        state = _make_state()
        state["draft_spec"] = None
        result = await oc._explain_node(state)
        assert result == {}

    @pytest.mark.asyncio
    async def test_intent_restatement_matches_spec(self):
        oc = _build_orchestrator()
        intent = "매일 오전 9시 보고서 발송"
        result = await oc._explain_node(_make_state(spec=_make_spec(intent)))
        explanation = result.get("workflow_explanation")
        assert explanation.intent_restatement == intent

    @pytest.mark.asyncio
    async def test_steps_count_matches_nodes(self):
        cfg = _make_node_config()
        inst = _make_instance(cfg.node_id)
        workflow = _make_workflow([inst])
        result = await _build_orchestrator()._explain_node(_make_state(workflow=workflow, node_candidates=[cfg]))
        assert len(result["workflow_explanation"].steps) == 1

    @pytest.mark.asyncio
    async def test_permissions_extracted(self):
        cfg = _make_node_config(required_connections=["slack"])
        inst = _make_instance(cfg.node_id)
        workflow = _make_workflow([inst])
        result = await _build_orchestrator()._explain_node(_make_state(workflow=workflow, node_candidates=[cfg]))
        perms = result["workflow_explanation"].permissions
        assert any(p.connection == "slack" for p in perms)

    @pytest.mark.asyncio
    async def test_node_missing_from_candidates_resolved_via_registry(self):
        """후보에 없는 노드(스킬/스켈레톤 주입)는 registry로 이름 복원 — instance_id 폴백 금지."""
        cfg = _make_node_config(name="pdf_generate")
        inst = _make_instance(cfg.node_id)
        workflow = _make_workflow([inst])
        oc = _build_orchestrator()
        oc._node_registry.get_schema = AsyncMock(return_value=cfg)
        # node_candidates를 비워 후보 미포함 상황 재현
        result = await oc._explain_node(_make_state(workflow=workflow, node_candidates=[]))
        step = result["workflow_explanation"].steps[0]
        assert step.node_name == "pdf_generate"
        assert step.node_name != inst.instance_id.hex[:8]
        oc._node_registry.get_schema.assert_awaited_once_with(cfg.node_id)

    @pytest.mark.asyncio
    async def test_registry_failure_falls_back_gracefully(self):
        """registry 조회 실패 시에도 explain은 죽지 않고 진행(graceful skip)."""
        cfg = _make_node_config()
        inst = _make_instance(cfg.node_id)
        workflow = _make_workflow([inst])
        oc = _build_orchestrator()
        oc._node_registry.get_schema = AsyncMock(side_effect=RuntimeError("registry down"))
        result = await oc._explain_node(_make_state(workflow=workflow, node_candidates=[]))
        assert isinstance(result.get("workflow_explanation"), WorkflowExplanation)
        assert len(result["workflow_explanation"].steps) == 1


# ------------------------------------------------------------------ _user_confirm_node tests


class TestUserConfirmNodeWithExplanation:
    @pytest.mark.asyncio
    async def test_explanation_included_in_result_frame(self):
        oc = _build_orchestrator()
        cfg = _make_node_config()
        inst = _make_instance(cfg.node_id)
        explanation = WorkflowExplanation(
            intent_restatement="슬랙 알림",
            summary="1개 노드",
            steps=[],
            permissions=[],
            assumptions=[],
        )
        state = _make_state(workflow=_make_workflow([inst]), node_candidates=[cfg])
        state["workflow_explanation"] = explanation
        result = await oc._user_confirm_node(state)
        frames = [f for f in result["collected_frames"] if isinstance(f, ResultFrame)]
        assert len(frames) == 1
        assert frames[0].payload["explanation"] is not None
        assert frames[0].payload["explanation"]["intent_restatement"] == "슬랙 알림"

    @pytest.mark.asyncio
    async def test_explanation_none_when_not_set(self):
        oc = _build_orchestrator()
        state = _make_state()
        state["workflow_explanation"] = None
        result = await oc._user_confirm_node(state)
        frames = [f for f in result["collected_frames"] if isinstance(f, ResultFrame)]
        assert frames[0].payload["explanation"] is None

    @pytest.mark.asyncio
    async def test_workflow_id_still_included(self):
        oc = _build_orchestrator()
        state = _make_state()
        wf_id = uuid4()
        state["saved_workflow_id"] = wf_id
        result = await oc._user_confirm_node(state)
        frames = [f for f in result["collected_frames"] if isinstance(f, ResultFrame)]
        assert frames[0].payload["workflow_id"] == str(wf_id)

    @pytest.mark.asyncio
    async def test_status_is_ready_to_execute(self):
        oc = _build_orchestrator()
        result = await oc._user_confirm_node(_make_state())
        frames = [f for f in result["collected_frames"] if isinstance(f, ResultFrame)]
        assert frames[0].payload["status"] == "ready_to_execute"
