"""retriever_node 단위 테스트 — 기본 노드 검색 + 커스텀 스킬 합산 / 중복 제거 / 실패 폴백."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from common_schemas.enums import RiskLevel
from common_schemas.workflow import NodeConfig

from ai_agent.adapters.langgraph.composer_graph import LangGraphOrchestrator
from ai_agent.domain.ports.node_registry import NodeRegistry
from ai_agent.domain.ports.workflow_repository import WorkflowRepository
from ai_agent.domain.services import (
    DrafterService,
    IntentAnalyzerService,
    QAEvaluatorService,
    SlotFillingService,
)


def _node_config(node_id=None, name="test_node") -> NodeConfig:
    return NodeConfig(
        node_id=node_id or uuid4(),
        node_type="test_type",
        name=name,
        category="test",
        version="1.0.0",
        input_schema={},
        output_schema={},
        parameter_schema={},
        risk_level=RiskLevel.LOW,
        required_connections=[],
        description="test node",
        is_mvp=True,
    )


def _build_orchestrator(embedder=None, skill_search=None) -> LangGraphOrchestrator:
    from nodes_graph.domain.services.graph_validator import GraphValidator

    node_registry = AsyncMock(spec=NodeRegistry)
    node_registry.search = AsyncMock(return_value=[_node_config(name="slack_trigger")])

    return LangGraphOrchestrator(
        intent_analyzer=AsyncMock(spec=IntentAnalyzerService),
        drafter=AsyncMock(spec=DrafterService),
        qa_evaluator=AsyncMock(spec=QAEvaluatorService),
        slot_filler=SlotFillingService(),
        node_registry=node_registry,
        workflow_repo=AsyncMock(spec=WorkflowRepository),
        graph_validator=AsyncMock(spec=GraphValidator),
        embedder=embedder,
        skill_search=skill_search,
    )


def _make_state(query: str = "슬랙 알림 보내줘") -> dict:
    from common_schemas.agent import DraftSpec, SlotFillingState

    return {
        "session_id": uuid4(),
        "user_id": uuid4(),
        "user_role": "User",
        "department_id": None,
        "messages": [{"role": "user", "content": query}],
        "turn_count": 1,
        "personal_memory": [],
        "intent": "draft",
        "intent_analyzed_entities": {},
        "draft_spec": DraftSpec(
            natural_language_intent=query,
            unresolved_nodes=[],
            discovered_entities={},
            slot_filling_state=SlotFillingState(asked=[], pending=[], filled={}),
            consultant_turn_count=0,
        ),
        "node_candidates": [],
        "workflow_draft": None,
        "qa_attempts": 0,
        "qa_score": 0.0,
        "pass_flag": False,
        "qa_feedback": "",
        "collected_frames": [],
        "error": None,
    }


class TestRetrieverNodeBasic:
    @pytest.mark.asyncio
    async def test_returns_node_candidates_from_registry(self):
        oc = _build_orchestrator()
        result = await oc._retriever_node(_make_state())
        assert len(result["node_candidates"]) == 1
        assert result["node_candidates"][0].name == "slack_trigger"

    @pytest.mark.asyncio
    async def test_emits_pipeline_status_frame(self):
        from common_schemas.transport import PipelineStatusFrame

        oc = _build_orchestrator()
        result = await oc._retriever_node(_make_state())
        frames = [f for f in result.get("collected_frames", []) if isinstance(f, PipelineStatusFrame)]
        assert len(frames) == 1
        assert frames[0].service_name == "retriever"
        assert frames[0].status == "completed"


class TestRetrieverNodeSkillSearch:
    def _make_skill(self, node_definition_id=None):
        skill = MagicMock()
        skill.node_definition_id = node_definition_id or uuid4()
        return skill

    @pytest.mark.asyncio
    async def test_skill_candidates_merged_with_registry(self):
        """스킬 마켓플레이스 결과가 기본 노드 후보에 합산된다."""
        skill_node_id = uuid4()
        skill_node = _node_config(node_id=skill_node_id, name="custom_skill_node")

        embedder = AsyncMock()
        embedder.embed = AsyncMock(return_value=[0.1] * 768)

        skill_search = AsyncMock()
        skill_search.execute_accessible = AsyncMock(return_value=[self._make_skill(skill_node_id)])

        node_registry = AsyncMock(spec=NodeRegistry)
        node_registry.search = AsyncMock(return_value=[_node_config(name="slack_trigger")])
        node_registry.get_schema = AsyncMock(return_value=skill_node)

        from nodes_graph.domain.services.graph_validator import GraphValidator

        oc = LangGraphOrchestrator(
            intent_analyzer=AsyncMock(spec=IntentAnalyzerService),
            drafter=AsyncMock(spec=DrafterService),
            qa_evaluator=AsyncMock(spec=QAEvaluatorService),
            slot_filler=SlotFillingService(),
            node_registry=node_registry,
            workflow_repo=AsyncMock(spec=WorkflowRepository),
            graph_validator=AsyncMock(spec=GraphValidator),
            embedder=embedder,
            skill_search=skill_search,
        )

        result = await oc._retriever_node(_make_state())
        names = [c.name for c in result["node_candidates"]]
        assert "slack_trigger" in names
        assert "custom_skill_node" in names

    @pytest.mark.asyncio
    async def test_duplicate_node_id_deduplicated(self):
        """기본 노드와 스킬 노드의 node_id가 같으면 중복 추가 안 됨."""
        shared_id = uuid4()
        base_node = _node_config(node_id=shared_id, name="shared_node")
        skill_node = _node_config(node_id=shared_id, name="shared_node")

        embedder = AsyncMock()
        embedder.embed = AsyncMock(return_value=[0.1] * 768)

        skill_search = AsyncMock()
        skill_search.execute_accessible = AsyncMock(return_value=[self._make_skill(shared_id)])

        node_registry = AsyncMock(spec=NodeRegistry)
        node_registry.search = AsyncMock(return_value=[base_node])
        node_registry.get_schema = AsyncMock(return_value=skill_node)

        from nodes_graph.domain.services.graph_validator import GraphValidator

        oc = LangGraphOrchestrator(
            intent_analyzer=AsyncMock(spec=IntentAnalyzerService),
            drafter=AsyncMock(spec=DrafterService),
            qa_evaluator=AsyncMock(spec=QAEvaluatorService),
            slot_filler=SlotFillingService(),
            node_registry=node_registry,
            workflow_repo=AsyncMock(spec=WorkflowRepository),
            graph_validator=AsyncMock(spec=GraphValidator),
            embedder=embedder,
            skill_search=skill_search,
        )

        result = await oc._retriever_node(_make_state())
        assert len(result["node_candidates"]) == 1

    @pytest.mark.asyncio
    async def test_skill_search_failure_falls_back_to_registry(self):
        """스킬 검색 실패해도 기본 노드 후보로 정상 반환."""
        embedder = AsyncMock()
        embedder.embed = AsyncMock(side_effect=Exception("embedding 서버 오류"))

        skill_search = AsyncMock()

        oc = _build_orchestrator(embedder=embedder, skill_search=skill_search)
        result = await oc._retriever_node(_make_state())

        assert result.get("error") is None
        assert len(result["node_candidates"]) == 1
        assert result["node_candidates"][0].name == "slack_trigger"

    @pytest.mark.asyncio
    async def test_no_embedder_skips_skill_search(self):
        """embedder 미주입 시 스킬 검색 건너뜀 — 기본 노드만 반환."""
        skill_search = AsyncMock()
        oc = _build_orchestrator(embedder=None, skill_search=skill_search)
        result = await oc._retriever_node(_make_state())
        skill_search.execute_accessible.assert_not_called()
        assert len(result["node_candidates"]) == 1


class TestRetrieverPersonalRecall:
    """REQ-004 개인화 배선 — retriever가 RAG로 사용자 패턴을 회수해 state에 싣는다."""

    def _orchestrator(self, embedder, personal_memory_store):
        from nodes_graph.domain.services.graph_validator import GraphValidator

        node_registry = AsyncMock(spec=NodeRegistry)
        node_registry.search = AsyncMock(return_value=[_node_config(name="slack_trigger")])
        return LangGraphOrchestrator(
            intent_analyzer=AsyncMock(spec=IntentAnalyzerService),
            drafter=AsyncMock(spec=DrafterService),
            qa_evaluator=AsyncMock(spec=QAEvaluatorService),
            slot_filler=SlotFillingService(),
            node_registry=node_registry,
            workflow_repo=AsyncMock(spec=WorkflowRepository),
            graph_validator=AsyncMock(spec=GraphValidator),
            embedder=embedder,
            skill_search=None,  # 스킬 검색은 끄고 개인 회수만 검증
            personal_memory_store=personal_memory_store,
        )

    def _store_returning(self, body: str, vec: list[float]):
        from ai_agent.domain.entities.memory_file import MemoryFile, MemoryFileRef

        store = AsyncMock()
        store.load_index = AsyncMock(
            return_value=[MemoryFileRef(name="p1", filename="p1.md", description="알림 선호")]
        )
        store.load_embedding = AsyncMock(return_value=vec)
        store.load_file = AsyncMock(
            return_value=MemoryFile(
                filename="p1.md", name="p1", description="알림 선호",
                memory_type="user", body=body,
            )
        )
        return store

    @pytest.mark.asyncio
    async def test_recalled_patterns_populate_state_and_emit_frame(self):
        from common_schemas.transport import RationaleDeltaFrame

        vec = [0.1] * 768  # query·file 동일 벡터 → 코사인 1.0 ≥ min_score(0.5)
        embedder = AsyncMock()
        embedder.embed = AsyncMock(return_value=vec)
        store = self._store_returning("Slack 알림은 항상 #automation 채널로", vec)

        oc = self._orchestrator(embedder, store)
        result = await oc._retriever_node(_make_state())

        assert result["personal_patterns"]
        assert "#automation" in result["personal_patterns"][0]
        assert any(
            isinstance(f, RationaleDeltaFrame) and "패턴" in f.delta
            for f in result["collected_frames"]
        )

    @pytest.mark.asyncio
    async def test_no_store_yields_empty_patterns_no_frame(self):
        from common_schemas.transport import RationaleDeltaFrame

        oc = self._orchestrator(embedder=None, personal_memory_store=None)
        result = await oc._retriever_node(_make_state())
        assert result["personal_patterns"] == []
        assert not any(
            isinstance(f, RationaleDeltaFrame) and "패턴" in f.delta
            for f in result["collected_frames"]
        )

    @pytest.mark.asyncio
    async def test_recall_failure_is_non_fatal(self):
        embedder = AsyncMock()
        embedder.embed = AsyncMock(side_effect=Exception("embedding 서버 오류"))
        store = self._store_returning("무시될 본문", [0.1] * 768)

        oc = self._orchestrator(embedder, store)
        result = await oc._retriever_node(_make_state())
        # 회수 실패해도 노드 후보는 정상 + 개인 패턴만 비어 반환
        assert result.get("error") is None
        assert result["personal_patterns"] == []
        assert len(result["node_candidates"]) == 1
