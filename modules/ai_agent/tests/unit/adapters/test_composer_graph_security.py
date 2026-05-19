"""security_node 단위 테스트 — 빈 메시지 / 길이 초과 / 정상 입력."""
from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from common_schemas.transport import PipelineStatusFrame

from ai_agent.adapters.langgraph.composer_graph import LangGraphOrchestrator
from ai_agent.domain.ports.node_registry import NodeRegistry
from ai_agent.domain.ports.workflow_repository import WorkflowRepository
from ai_agent.domain.services import (
    DrafterService,
    IntentAnalyzerService,
    QAEvaluatorService,
    SlotFillingService,
)


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


def _make_state(content: str) -> dict:
    return {
        "session_id": uuid4(),
        "user_id": uuid4(),
        "messages": [{"role": "user", "content": content}],
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
        "collected_frames": [],
        "error": None,
    }


class TestSecurityNode:
    @pytest.mark.asyncio
    async def test_empty_message_returns_error(self):
        oc = _build_orchestrator()
        result = await oc._security_node(_make_state("   "))
        assert "error" in result
        assert result["error"]

    @pytest.mark.asyncio
    async def test_message_too_long_returns_error(self):
        oc = _build_orchestrator()
        result = await oc._security_node(_make_state("a" * 10_001))
        assert "error" in result
        assert "10,000" in result["error"]

    @pytest.mark.asyncio
    async def test_valid_message_emits_pipeline_status_frame(self):
        oc = _build_orchestrator()
        result = await oc._security_node(_make_state("슬랙으로 보고서 보내줘"))
        assert "error" not in result or result.get("error") is None
        frames = result.get("collected_frames", [])
        status_frames = [f for f in frames if isinstance(f, PipelineStatusFrame)]
        assert len(status_frames) == 1
        assert status_frames[0].service_name == "security"
        assert status_frames[0].status == "completed"
        assert status_frames[0].elapsed_ms is not None

    @pytest.mark.asyncio
    async def test_exact_10000_chars_passes(self):
        oc = _build_orchestrator()
        result = await oc._security_node(_make_state("a" * 10_000))
        assert result.get("error") is None

    @pytest.mark.asyncio
    async def test_empty_messages_list_returns_error(self):
        oc = _build_orchestrator()
        state = _make_state("dummy")
        state["messages"] = []
        result = await oc._security_node(state)
        assert "error" in result
