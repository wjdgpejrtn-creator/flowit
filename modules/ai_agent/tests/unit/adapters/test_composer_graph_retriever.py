"""retriever_node 단위 테스트 — 기본 노드 검색 + 개인 패턴 RAG 회수 + 스킬 미합산(#372 결함 B) + GraphRAG(ADR-0026)."""
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


class TestRetrieverExpandCanFollow:
    """ADR-0026 §4.2a — expand_candidates(CAN_FOLLOW 서브그래프)를 호출해 후행 노드를 검색
    후보에 **ADD 보강**한다. ADD 전용(subtract 금지) + 실패 비치명적."""

    def _orchestrator_with_retriever(
        self, search_result, ontology_retriever, list_by_node_types=None
    ):
        from nodes_graph.domain.services.graph_validator import GraphValidator

        node_registry = AsyncMock(spec=NodeRegistry)
        node_registry.search = AsyncMock(return_value=search_result)
        node_registry.list_structural = AsyncMock(return_value=[])
        node_registry.list_by_node_types = AsyncMock(return_value=list_by_node_types or [])
        return LangGraphOrchestrator(
            intent_analyzer=AsyncMock(spec=IntentAnalyzerService),
            drafter=AsyncMock(spec=DrafterService),
            qa_evaluator=AsyncMock(spec=QAEvaluatorService),
            slot_filler=SlotFillingService(),
            node_registry=node_registry,
            workflow_repo=AsyncMock(spec=WorkflowRepository),
            graph_validator=AsyncMock(spec=GraphValidator),
            ontology_retriever=ontology_retriever,
        )

    def _subgraph(self, adjacency):
        from ai_agent.domain.value_objects.ontology import OntologySubgraph

        return OntologySubgraph(seeds=tuple(adjacency), nodes=(), adjacency=adjacency)

    @pytest.mark.asyncio
    async def test_can_follow_neighbors_added_to_candidates(self):
        """CAN_FOLLOW 후행 노드가 그라운딩돼 후보에 ADD된다."""
        seed = _node_config(name="csv_parse")
        seed.__dict__["node_type"] = "csv_parse"
        neighbor = _node_config(name="csv_build")
        neighbor.__dict__["node_type"] = "csv_build"

        ontology_retriever = AsyncMock()
        ontology_retriever.match_patterns = AsyncMock(return_value=[])
        ontology_retriever.expand_candidates = AsyncMock(
            return_value=self._subgraph({"csv_parse": ("csv_build",)})
        )

        oc = self._orchestrator_with_retriever(
            [seed], ontology_retriever, list_by_node_types=[neighbor]
        )
        result = await oc._retriever_node(_make_state())

        ontology_retriever.expand_candidates.assert_called_once()
        # 그라운딩은 seed에 이미 없는 후행 node_type만 대상으로 호출
        oc._node_registry.list_by_node_types.assert_awaited_once_with(["csv_build"])
        types_in_result = {c.node_type for c in result["node_candidates"]}
        assert types_in_result == {"csv_parse", "csv_build"}

    @pytest.mark.asyncio
    async def test_candidates_never_filtered(self):
        """후보는 온톨로지로 subtract 필터링되지 않는다 — ETL stale 노드도 보존(ADD 전용)."""
        candidate_a = _node_config(name="slack_send")
        candidate_a.__dict__["node_type"] = "slack_send"
        candidate_b = _node_config(name="new_node_not_in_neo4j")
        candidate_b.__dict__["node_type"] = "new_node_not_in_neo4j"

        ontology_retriever = AsyncMock()
        ontology_retriever.match_patterns = AsyncMock(return_value=[])
        ontology_retriever.expand_candidates = AsyncMock(return_value=self._subgraph({}))

        oc = self._orchestrator_with_retriever([candidate_a, candidate_b], ontology_retriever)
        result = await oc._retriever_node(_make_state())

        types_in_result = {c.node_type for c in result["node_candidates"]}
        assert "slack_send" in types_in_result
        assert "new_node_not_in_neo4j" in types_in_result  # stale여도 보존

    @pytest.mark.asyncio
    async def test_expansion_is_capped_and_seeds_from_search_hits_only(self):
        """풀 비대 가드 — seed는 검색 hit만(구조노드 제외), 추가는 _EXPAND_ADD_LIMIT로 cap."""
        from ai_agent.adapters.langgraph.composer_graph import (
            _EXPAND_ADD_LIMIT,
            _EXPAND_SEED_LIMIT,
        )

        # 검색 hit 6개(상위 seed 제한 검증) + 구조노드 1개(seed 제외 검증)
        search_hits = []
        for i in range(6):
            c = _node_config(name=f"hit{i}")
            c.__dict__["node_type"] = f"hit{i}"
            search_hits.append(c)
        structural = _node_config(name="schedule_trigger")
        structural.__dict__["node_type"] = "schedule_trigger"

        # 각 seed가 여러 후행을 갖게 해 cap 동작을 강제
        adjacency = {f"hit{i}": (f"succ{i}a", f"succ{i}b") for i in range(6)}
        adjacency["schedule_trigger"] = ("trig_succ",)  # 구조노드 후행 — seed면 잡힘

        ontology_retriever = AsyncMock()
        ontology_retriever.match_patterns = AsyncMock(return_value=[])
        ontology_retriever.expand_candidates = AsyncMock(return_value=self._subgraph(adjacency))

        ground_ret = [_node_config(name="g")]
        ground_ret[0].__dict__["node_type"] = "g"

        from nodes_graph.domain.services.graph_validator import GraphValidator

        node_registry = AsyncMock(spec=NodeRegistry)
        node_registry.search = AsyncMock(return_value=search_hits)
        node_registry.list_structural = AsyncMock(return_value=[structural])
        node_registry.list_by_node_types = AsyncMock(return_value=ground_ret)
        oc = LangGraphOrchestrator(
            intent_analyzer=AsyncMock(spec=IntentAnalyzerService),
            drafter=AsyncMock(spec=DrafterService),
            qa_evaluator=AsyncMock(spec=QAEvaluatorService),
            slot_filler=SlotFillingService(),
            node_registry=node_registry,
            workflow_repo=AsyncMock(spec=WorkflowRepository),
            graph_validator=AsyncMock(spec=GraphValidator),
            ontology_retriever=ontology_retriever,
        )

        await oc._retriever_node(_make_state())

        # seed = 검색 상위 hit만, _EXPAND_SEED_LIMIT개로 제한(구조노드 schedule_trigger 미포함)
        seeds_arg = ontology_retriever.expand_candidates.call_args.args[0]
        assert "schedule_trigger" not in seeds_arg
        assert len(seeds_arg) <= _EXPAND_SEED_LIMIT
        assert seeds_arg == [f"hit{i}" for i in range(_EXPAND_SEED_LIMIT)]
        # 그라운딩 대상(추가 후보)은 _EXPAND_ADD_LIMIT개로 cap
        grounded_arg = node_registry.list_by_node_types.call_args.args[0]
        assert len(grounded_arg) == _EXPAND_ADD_LIMIT

    @pytest.mark.asyncio
    async def test_expand_failure_is_non_fatal(self):
        """expand_candidates 실패해도 검색 후보는 정상 반환(비치명적)."""
        seed = _node_config(name="slack_send")
        seed.__dict__["node_type"] = "slack_send"

        ontology_retriever = AsyncMock()
        ontology_retriever.match_patterns = AsyncMock(return_value=[])
        ontology_retriever.expand_candidates = AsyncMock(side_effect=Exception("Neo4j 오류"))

        oc = self._orchestrator_with_retriever([seed], ontology_retriever)
        result = await oc._retriever_node(_make_state())

        assert result.get("error") is None
        assert {c.node_type for c in result["node_candidates"]} == {"slack_send"}


class TestRetrieverMotifGrounding:
    """ADR-0026 Phase 2 — OntologyRetrieverPort.match_patterns 연동 테스트."""

    def _make_pattern(self, name: str, slots: dict):
        from ai_agent.domain.value_objects.ontology import PatternTemplate

        return PatternTemplate(name=name, intent="검증", role_slots=slots)

    def _orchestrator_with_retriever(self, ontology_retriever):
        from nodes_graph.domain.services.graph_validator import GraphValidator

        node_registry = AsyncMock(spec=NodeRegistry)
        node_registry.search = AsyncMock(return_value=[_node_config(name="slack_send")])
        node_registry.list_structural = AsyncMock(return_value=[])
        node_registry.list_by_node_types = AsyncMock(return_value=[])
        # 모티프 테스트는 expand 경로가 관심 밖 — 빈 서브그래프로 기본화(비치명적 경로 미발동).
        if ontology_retriever is not None:
            from ai_agent.domain.value_objects.ontology import OntologySubgraph

            ontology_retriever.expand_candidates = AsyncMock(
                return_value=OntologySubgraph(seeds=(), nodes=(), adjacency={})
            )
        return LangGraphOrchestrator(
            intent_analyzer=AsyncMock(spec=IntentAnalyzerService),
            drafter=AsyncMock(spec=DrafterService),
            qa_evaluator=AsyncMock(spec=QAEvaluatorService),
            slot_filler=SlotFillingService(),
            node_registry=node_registry,
            workflow_repo=AsyncMock(spec=WorkflowRepository),
            graph_validator=AsyncMock(spec=GraphValidator),
            ontology_retriever=ontology_retriever,
        )

    @pytest.mark.asyncio
    async def test_pattern_templates_stored_in_state(self):
        """match_patterns 결과가 state에 pattern_templates로 저장된다."""
        pattern = self._make_pattern("quality_gate_loop", {"generator": ("llm_generate",)})
        ontology_retriever = AsyncMock()
        ontology_retriever.match_patterns = AsyncMock(return_value=[pattern])

        oc = self._orchestrator_with_retriever(ontology_retriever)
        result = await oc._retriever_node(_make_state("검증 후 재생성"))

        ontology_retriever.match_patterns.assert_called_once()
        assert result["pattern_templates"] == [pattern]

    @pytest.mark.asyncio
    async def test_match_patterns_failure_is_non_fatal(self):
        """match_patterns 실패 시 pattern_templates=None, 노드 후보는 정상 반환."""
        ontology_retriever = AsyncMock()
        ontology_retriever.match_patterns = AsyncMock(side_effect=Exception("Neo4j 오류"))

        oc = self._orchestrator_with_retriever(ontology_retriever)
        result = await oc._retriever_node(_make_state())

        assert result.get("error") is None
        assert result["pattern_templates"] is None
        assert len(result["node_candidates"]) >= 1

    @pytest.mark.asyncio
    async def test_no_ontology_retriever_pattern_templates_none(self):
        """ontology_retriever 미주입 시 pattern_templates=None."""
        oc = self._orchestrator_with_retriever(ontology_retriever=None)
        result = await oc._retriever_node(_make_state())

        assert result["pattern_templates"] is None

    @pytest.mark.asyncio
    async def test_empty_patterns_stored_as_empty_list(self):
        """:Pattern 노드 없으면 빈 리스트가 저장된다 (ETL 시드 전 정상 동작)."""
        ontology_retriever = AsyncMock()
        ontology_retriever.match_patterns = AsyncMock(return_value=[])

        oc = self._orchestrator_with_retriever(ontology_retriever)
        result = await oc._retriever_node(_make_state())

        assert result["pattern_templates"] == []


class TestDrafterSkillComposerInstructions:
    """ADR-0024 D5 — COMPOSER.md 로더 배선: skill 선택 시 composer_instructions가 drafter에 주입된다."""

    def _ai_node_config(self) -> NodeConfig:
        return NodeConfig(
            node_id=uuid4(), node_type="gemma_chat", name="gemma_chat",
            category="ai", version="1.0", input_schema={}, output_schema={},
            parameter_schema={}, risk_level=RiskLevel.LOW, required_connections=[],
            description="LLM node", is_mvp=True,
        )

    def _build_oc_with_skill_doc_store(self, skill_doc_store):
        from nodes_graph.domain.services.graph_validator import GraphValidator

        node_registry = AsyncMock(spec=NodeRegistry)
        node_registry.search = AsyncMock(return_value=[self._ai_node_config()])
        node_registry.list_structural = AsyncMock(return_value=[])
        node_registry.list_by_node_types = AsyncMock(return_value=[])
        return LangGraphOrchestrator(
            intent_analyzer=AsyncMock(spec=IntentAnalyzerService),
            drafter=AsyncMock(spec=DrafterService),
            qa_evaluator=AsyncMock(spec=QAEvaluatorService),
            slot_filler=SlotFillingService(),
            node_registry=node_registry,
            workflow_repo=AsyncMock(spec=WorkflowRepository),
            graph_validator=AsyncMock(spec=GraphValidator),
            skill_doc_store=skill_doc_store,
        )

    def _make_skill_state(self, skill_id=None):
        from common_schemas import SkillDocument

        sid = skill_id or uuid4()
        state = _make_state("스킬 기반 워크플로우")
        state["selected_skill_id"] = sid
        state["offered_skill_ids"] = [str(sid)]
        state["node_candidates"] = [self._ai_node_config()]
        return state, sid

    @pytest.mark.asyncio
    async def test_composer_instructions_passed_to_drafter(self):
        """SkillDocumentStore가 composer_instructions 있는 문서 반환 → drafter에 주입된다 (D5)."""
        from common_schemas import SkillDocument
        from skills_marketplace.domain.ports import SkillDocumentStore

        sid = uuid4()
        doc = SkillDocument(
            skill_id=sid, name="테스트 스킬", description="설명",
            composer_instructions="LLM 노드 + Email 노드를 순서대로 엮어야 합니다.",
        )
        skill_doc_store = AsyncMock(spec=SkillDocumentStore)
        skill_doc_store.load = AsyncMock(return_value=doc)

        oc = self._build_oc_with_skill_doc_store(skill_doc_store)
        state, _ = self._make_skill_state(skill_id=sid)
        oc._drafter.draft = AsyncMock(return_value=AsyncMock(nodes=[], connections=[]))

        await oc._drafter_node(state)

        call_kwargs = oc._drafter.draft.call_args.kwargs
        assert call_kwargs.get("skill_composer_instructions") == "LLM 노드 + Email 노드를 순서대로 엮어야 합니다."

    @pytest.mark.asyncio
    async def test_empty_composer_instructions_treated_as_none(self):
        """composer_instructions가 빈 문자열이면 None으로 처리한다."""
        from common_schemas import SkillDocument
        from skills_marketplace.domain.ports import SkillDocumentStore

        sid = uuid4()
        doc = SkillDocument(skill_id=sid, name="스킬", description="설명", composer_instructions="")
        skill_doc_store = AsyncMock(spec=SkillDocumentStore)
        skill_doc_store.load = AsyncMock(return_value=doc)

        oc = self._build_oc_with_skill_doc_store(skill_doc_store)
        state, _ = self._make_skill_state(skill_id=sid)
        oc._drafter.draft = AsyncMock(return_value=AsyncMock(nodes=[], connections=[]))

        await oc._drafter_node(state)

        call_kwargs = oc._drafter.draft.call_args.kwargs
        assert call_kwargs.get("skill_composer_instructions") is None

    @pytest.mark.asyncio
    async def test_no_skill_doc_store_passes_none(self):
        """SkillDocumentStore 미주입 시 skill_composer_instructions=None으로 drafter 호출."""
        oc = self._build_oc_with_skill_doc_store(skill_doc_store=None)
        state, _ = self._make_skill_state()
        oc._drafter.draft = AsyncMock(return_value=AsyncMock(nodes=[], connections=[]))

        await oc._drafter_node(state)

        call_kwargs = oc._drafter.draft.call_args.kwargs
        assert call_kwargs.get("skill_composer_instructions") is None

    @pytest.mark.asyncio
    async def test_skill_doc_store_failure_is_non_fatal(self):
        """SkillDocumentStore.load 실패 시 non-fatal — drafter는 None으로 호출된다."""
        from skills_marketplace.domain.ports import SkillDocumentStore

        skill_doc_store = AsyncMock(spec=SkillDocumentStore)
        skill_doc_store.load = AsyncMock(side_effect=Exception("GCS 오류"))

        oc = self._build_oc_with_skill_doc_store(skill_doc_store)
        state, _ = self._make_skill_state()
        oc._drafter.draft = AsyncMock(return_value=AsyncMock(nodes=[], connections=[]))

        await oc._drafter_node(state)

        call_kwargs = oc._drafter.draft.call_args.kwargs
        assert call_kwargs.get("skill_composer_instructions") is None
