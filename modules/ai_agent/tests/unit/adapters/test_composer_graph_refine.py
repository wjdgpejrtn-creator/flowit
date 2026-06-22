"""_drafter_node 대화형 refine 배선 — 이전 워크플로우 로드 + 후보 보강 + drafter 전달 (C)."""
from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from common_schemas import NodeInstance, Position, WorkflowSchema
from common_schemas.agent import DraftSpec, SlotFillingState
from common_schemas.enums import RiskLevel
from common_schemas.workflow import NodeConfig

from ai_agent.adapters.langgraph.composer_graph import LangGraphOrchestrator
from ai_agent.domain.ports.node_registry import NodeRegistry
from ai_agent.domain.ports.workflow_draft_store import WorkflowDraftStore
from ai_agent.domain.ports.workflow_repository import WorkflowRepository
from ai_agent.domain.services import (
    DrafterService,
    IntentAnalyzerService,
    QAEvaluatorService,
    SlotFillingService,
)


def _node_config(node_id=None, node_type="http", name="HTTP") -> NodeConfig:
    return NodeConfig(
        node_id=node_id or uuid4(),
        node_type=node_type,
        name=name,
        category="test",
        version="1.0.0",
        input_schema={},
        output_schema={},
        parameter_schema={},
        risk_level=RiskLevel.LOW,
        required_connections=[],
        description="",
        is_mvp=True,
    )


def _one_node_workflow(node_id, params) -> WorkflowSchema:
    return WorkflowSchema(
        workflow_id=uuid4(),
        name="WF",
        scope="private",
        is_draft=False,
        owner_user_id=uuid4(),
        nodes=[NodeInstance(instance_id=uuid4(), node_id=node_id, parameters=params, position=Position(x=0, y=0))],
        connections=[],
    )


def _build_orchestrator(draft_store=None) -> LangGraphOrchestrator:
    from nodes_graph.domain.services.graph_validator import GraphValidator

    node_registry = AsyncMock(spec=NodeRegistry)
    node_registry.search = AsyncMock(return_value=[])
    return LangGraphOrchestrator(
        intent_analyzer=AsyncMock(spec=IntentAnalyzerService),
        drafter=AsyncMock(spec=DrafterService),
        qa_evaluator=AsyncMock(spec=QAEvaluatorService),
        slot_filler=SlotFillingService(),
        node_registry=node_registry,
        workflow_repo=AsyncMock(spec=WorkflowRepository),
        graph_validator=AsyncMock(spec=GraphValidator),
        workflow_draft_store=draft_store,
    )


def _state(intent: str, session_id) -> dict:
    return {
        "session_id": session_id,
        "user_id": uuid4(),
        "user_role": "User",
        "department_id": None,
        "messages": [{"role": "user", "content": "url을 https://real.com 으로 바꿔줘"}],
        "turn_count": 2,
        "personal_memory": [],
        "intent": intent,
        "intent_analyzed_entities": {},
        "draft_spec": DraftSpec(
            natural_language_intent="url을 바꿔줘",
            unresolved_nodes=[],
            discovered_entities={},
            slot_filling_state=SlotFillingState(asked=[], pending=[], filled={}),
            consultant_turn_count=0,
        ),
        "node_candidates": [],  # search 결과 비어 — 기존 노드는 augment로 복원돼야 함
        "workflow_draft": None,
        "qa_attempts": 0,
        "qa_score": 0.0,
        "pass_flag": False,
        "qa_feedback": "",
        "collected_frames": [],
        "error": None,
    }


@pytest.mark.asyncio
async def test_refine_loads_prior_augments_candidates_and_passes_to_drafter():
    session_id = uuid4()
    prior_node_id = uuid4()
    prior = _one_node_workflow(prior_node_id, {"url": "https://old.com"})

    draft_store = AsyncMock(spec=WorkflowDraftStore)
    draft_store.load_draft = AsyncMock(return_value=prior)

    orch = _build_orchestrator(draft_store=draft_store)
    cfg = _node_config(node_id=prior_node_id, node_type="http")
    orch._node_registry.get_schema = AsyncMock(return_value=cfg)
    orch._drafter.draft = AsyncMock(return_value=_one_node_workflow(prior_node_id, {"url": "https://real.com"}))

    result = await orch._drafter_node(_state("refine", session_id))

    assert result.get("error") is None
    draft_store.load_draft.assert_awaited_once_with(session_id)
    orch._node_registry.get_schema.assert_awaited_once_with(prior_node_id)  # 후보 비어→복원
    orch._drafter.draft.assert_awaited_once()
    call = orch._drafter.draft.call_args
    assert call.kwargs["prior_workflow"] is prior            # 편집 컨텍스트 전달
    passed_candidates = call.args[1]                          # 보강된 후보에 기존 노드 포함
    assert any(c.node_id == prior_node_id for c in passed_candidates)


@pytest.mark.asyncio
async def test_draft_intent_does_not_load_prior():
    orch = _build_orchestrator(draft_store=AsyncMock(spec=WorkflowDraftStore))
    orch._drafter.draft = AsyncMock(return_value=_one_node_workflow(uuid4(), {}))

    await orch._drafter_node(_state("draft", uuid4()))

    orch._workflow_draft_store.load_draft.assert_not_awaited()  # fresh draft 경로
    assert orch._drafter.draft.call_args.kwargs["prior_workflow"] is None
