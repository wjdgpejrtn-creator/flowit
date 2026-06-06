"""retriever_node 단위 테스트 — 기본 노드 검색 + 개인 패턴 RAG 회수 + 스킬 미합산(#372 결함 B)."""
from __future__ import annotations

from unittest.mock import AsyncMock
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


class TestRetrieverNodeIgnoresSkills:
    """#372 결함 B — 스킬은 retriever에서 노드 후보로 합산되지 않는다.

    스킬은 실행 노드가 아니라 LLM 노드에 주입되는 지침서(모델 A)다. 스킬 검색·제시는
    two-shot 경로(`_suggest_skill_select_node`)가 전담하고, retriever는 순수 노드 카탈로그
    검색만 한다 — 스킬을 빈 껍데기 NodeDefinition 노드로 둔갑시키던 경로를 제거(#372 재현 증상).
    """

    @pytest.mark.asyncio
    async def test_skills_not_merged_into_candidates(self):
        """skill_search/embedder가 주입돼 있어도 retriever는 스킬을 검색·합산하지 않는다."""
        embedder = AsyncMock()
        embedder.embed = AsyncMock(return_value=[0.1] * 768)
        skill_search = AsyncMock()

        node_registry = AsyncMock(spec=NodeRegistry)
        node_registry.search = AsyncMock(return_value=[_node_config(name="slack_trigger")])

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

        # retriever는 스킬 검색을 호출하지 않고 노드 카탈로그 결과만 반환
        skill_search.execute_accessible.assert_not_called()
        names = [c.name for c in result["node_candidates"]]
        assert names == ["slack_trigger"]


class TestRetrieverStructuralUnion:
    """#378 후속 A — 구조 노드(트리거/제어흐름)는 의미검색 top-k에 안 떠도 항상 후보에 합산.

    "매주 월요일 9시에 …" 같은 요청에서 schedule_trigger가 검색에 안 잡혀 drafter가
    `후보 목록에 없는 node_type: schedule_trigger`로 하드페일하던 문제를 해소한다.
    """

    def _orchestrator(self, search_result, structural_result):
        from nodes_graph.domain.services.graph_validator import GraphValidator

        node_registry = AsyncMock(spec=NodeRegistry)
        node_registry.search = AsyncMock(return_value=search_result)
        node_registry.list_structural = AsyncMock(return_value=structural_result)
        return LangGraphOrchestrator(
            intent_analyzer=AsyncMock(spec=IntentAnalyzerService),
            drafter=AsyncMock(spec=DrafterService),
            qa_evaluator=AsyncMock(spec=QAEvaluatorService),
            slot_filler=SlotFillingService(),
            node_registry=node_registry,
            workflow_repo=AsyncMock(spec=WorkflowRepository),
            graph_validator=AsyncMock(spec=GraphValidator),
        )

    @pytest.mark.asyncio
    async def test_structural_nodes_appended_to_candidates(self):
        """검색이 schedule_trigger를 놓쳐도 구조 노드로 후보에 들어온다."""
        content = _node_config(name="slack_post_message")
        trigger = _node_config(name="schedule_trigger")
        oc = self._orchestrator(search_result=[content], structural_result=[trigger])

        result = await oc._retriever_node(_make_state())

        names = {c.name for c in result["node_candidates"]}
        assert "slack_post_message" in names
        assert "schedule_trigger" in names

    @pytest.mark.asyncio
    async def test_dedup_by_node_id(self):
        """검색 결과와 구조 노드가 겹치면(같은 node_id) 중복 없이 한 번만."""
        shared_id = uuid4()
        in_search = _node_config(node_id=shared_id, name="schedule_trigger")
        in_structural = _node_config(node_id=shared_id, name="schedule_trigger")
        oc = self._orchestrator(search_result=[in_search], structural_result=[in_structural])

        result = await oc._retriever_node(_make_state())

        ids = [c.node_id for c in result["node_candidates"]]
        assert ids.count(shared_id) == 1

    @pytest.mark.asyncio
    async def test_structural_fetch_failure_is_non_fatal(self):
        """구조 노드 조회 실패해도 검색 후보는 정상 반환(비치명적)."""
        content = _node_config(name="slack_post_message")
        oc = self._orchestrator(search_result=[content], structural_result=[])
        oc._node_registry.list_structural = AsyncMock(side_effect=Exception("repo 오류"))

        result = await oc._retriever_node(_make_state())

        assert result.get("error") is None
        names = {c.name for c in result["node_candidates"]}
        assert names == {"slack_post_message"}


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
