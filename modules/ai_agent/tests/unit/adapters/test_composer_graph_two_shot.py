"""two-shot HITL 스킬 선택 바인딩 단위 테스트 (REQ-013).

커버리지:
  - suggest_skill_select: 옵션 emit+상태영속(two-shot) / 미주입·빈결과·store미주입 폴백(one-shot)
  - resume: GCS 복원 성공 / 만료(E_SESSION_EXPIRED)
  - bind_skill: 첫 LLM 노드 바인딩 / 선택없음 no-op / LLM 노드 0개 경고
  - 라우터: _route_entry / _route_after_resume / _route_after_suggest
  - resume state 직렬화 라운드트립
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from common_schemas.agent import DraftSpec, SlotFillingState
from common_schemas.enums import RiskLevel
from common_schemas.transport import ErrorFrame, SkillSelectionFrame
from common_schemas.workflow import NodeConfig, NodeInstance, Position, WorkflowSchema

from ai_agent.adapters.langgraph.composer_graph import LangGraphOrchestrator
from ai_agent.domain.ports.node_registry import NodeRegistry
from ai_agent.domain.ports.workflow_repository import WorkflowRepository
from ai_agent.domain.services import (
    DrafterService,
    IntentAnalyzerService,
    QAEvaluatorService,
    SlotFillingService,
)


def _node_config(node_id=None, name="test_node", category="test") -> NodeConfig:
    return NodeConfig(
        node_id=node_id or uuid4(),
        node_type="test_type",
        name=name,
        category=category,
        version="1.0.0",
        input_schema={},
        output_schema={},
        parameter_schema={},
        risk_level=RiskLevel.LOW,
        required_connections=[],
        description="test node",
        is_mvp=True,
    )


def _node_instance(node_id) -> NodeInstance:
    return NodeInstance(
        instance_id=uuid4(),
        node_id=node_id,
        parameters={},
        position=Position(x=0.0, y=0.0),
    )


def _workflow(nodes: list[NodeInstance]) -> WorkflowSchema:
    return WorkflowSchema(
        workflow_id=uuid4(),
        owner_user_id=uuid4(),
        name="wf",
        description=None,
        scope="private",
        is_draft=True,
        nodes=nodes,
        connections=[],
    )


def _build_orchestrator(embedder=None, skill_search=None, composer_state_store=None) -> LangGraphOrchestrator:
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
        composer_state_store=composer_state_store,
    )


def _state(**overrides) -> dict:
    query = overrides.pop("query", "슬랙 알림 보내줘")
    base = {
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
        "round": 1,
        "selected_skill_id": None,
        "awaiting_skill_selection": False,
        "resume_ok": False,
        "suggested_skills": [],
    }
    base.update(overrides)
    return base


def _skill(skill_id=None, name="요약 전문가", description="문서 요약 지침서", node_definition_id=None,
           owner_user_id=None):
    s = MagicMock()
    s.skill_id = skill_id or uuid4()
    s.name = name
    s.description = description
    s.node_definition_id = node_definition_id
    s.owner_user_id = owner_user_id  # 개인 스킬이면 owner 지정(company/team은 None) — is_personal 판별
    return s


# ---------------------------------------------------------------- suggest_skill_select


class TestSuggestSkillSelect:
    @pytest.mark.asyncio
    async def test_emits_frame_and_persists_state_when_options_found(self):
        embedder = AsyncMock()
        embedder.embed = AsyncMock(return_value=[0.1] * 768)
        skill_search = AsyncMock()
        skill_search.execute_accessible = AsyncMock(return_value=[_skill(name="요약가"), _skill(name="번역가")])
        store = AsyncMock()

        oc = _build_orchestrator(embedder=embedder, skill_search=skill_search, composer_state_store=store)
        st = _state()
        result = await oc._suggest_skill_select_node(st)

        assert result["awaiting_skill_selection"] is True
        frames = [f for f in result["collected_frames"] if isinstance(f, SkillSelectionFrame)]
        assert len(frames) == 1
        assert len(frames[0].options) == 2
        assert frames[0].allow_skip is True
        # 상태 영속 호출됨 — 제시 옵션 skill_id + user_id 포함(2차 검증 재료)
        store.save_state.assert_awaited_once()
        saved_session, saved_blob = store.save_state.await_args.args
        assert saved_session == st["session_id"]
        assert saved_blob["draft_spec"] is not None
        assert "node_candidates" in saved_blob
        assert saved_blob["user_id"] == str(st["user_id"])
        offered = {o.skill_id for o in frames[0].options}
        assert set(saved_blob["offered_skill_ids"]) == {str(s) for s in offered}

    @pytest.mark.asyncio
    async def test_personal_skill_flagged_company_not(self):
        """본인 소유 개인 스킬만 is_personal=True (프론트 ⭐ 자주 사용 배지 — REQ-013 개인화 추천)."""
        embedder = AsyncMock()
        embedder.embed = AsyncMock(return_value=[0.1] * 768)
        st = _state()
        mine = st["user_id"]
        skill_search = AsyncMock()
        skill_search.execute_accessible = AsyncMock(return_value=[
            _skill(name="내 개인 스킬", owner_user_id=mine),       # 본인 소유 → ⭐
            _skill(name="전사 스킬", owner_user_id=None),           # company → 배지 없음
            _skill(name="남의 개인 스킬", owner_user_id=uuid4()),   # 타인 소유 → 배지 없음
        ])
        oc = _build_orchestrator(embedder=embedder, skill_search=skill_search, composer_state_store=AsyncMock())

        result = await oc._suggest_skill_select_node(st)

        opts = {o.name: o.is_personal for o in result["collected_frames"][0].options}
        assert opts == {"내 개인 스킬": True, "전사 스킬": False, "남의 개인 스킬": False}

    @pytest.mark.asyncio
    async def test_refine_skips_skill_suggestion_without_search(self):
        # #369 후속: refine(기존 워크플로우 편집)은 two-shot 스킬 제안을 타면 안 된다.
        # "url/채널 수정해줘" 같은 편집 발화가 스킬 카드로 끊겨 새 생성처럼 보이던 버그 차단 —
        # intent=refine이면 검색조차 하지 않고 바로 draft로 진행(awaiting_skill_selection=False).
        embedder = AsyncMock()
        embedder.embed = AsyncMock(return_value=[0.1] * 768)
        skill_search = AsyncMock()
        skill_search.execute_accessible = AsyncMock(return_value=[_skill(name="요약가")])
        store = AsyncMock()

        oc = _build_orchestrator(embedder=embedder, skill_search=skill_search, composer_state_store=store)
        result = await oc._suggest_skill_select_node(_state(intent="refine"))

        assert result == {"awaiting_skill_selection": False}
        # 스킬 검색·상태 영속 자체가 호출되지 않아야 한다(편집 흐름 보존).
        skill_search.execute_accessible.assert_not_called()
        store.save_state.assert_not_called()

    @pytest.mark.asyncio
    async def test_fallback_when_skill_search_not_injected(self):
        oc = _build_orchestrator(embedder=None, skill_search=None, composer_state_store=AsyncMock())
        result = await oc._suggest_skill_select_node(_state())
        assert result == {"awaiting_skill_selection": False}

    @pytest.mark.asyncio
    async def test_fallback_when_no_options(self):
        embedder = AsyncMock()
        embedder.embed = AsyncMock(return_value=[0.1] * 768)
        skill_search = AsyncMock()
        skill_search.execute_accessible = AsyncMock(return_value=[])
        oc = _build_orchestrator(embedder=embedder, skill_search=skill_search, composer_state_store=AsyncMock())
        result = await oc._suggest_skill_select_node(_state())
        assert result["awaiting_skill_selection"] is False

    @pytest.mark.asyncio
    async def test_fallback_when_state_store_not_injected(self):
        embedder = AsyncMock()
        embedder.embed = AsyncMock(return_value=[0.1] * 768)
        skill_search = AsyncMock()
        skill_search.execute_accessible = AsyncMock(return_value=[_skill()])
        oc = _build_orchestrator(embedder=embedder, skill_search=skill_search, composer_state_store=None)
        result = await oc._suggest_skill_select_node(_state())
        assert result["awaiting_skill_selection"] is False

    @pytest.mark.asyncio
    async def test_fallback_on_search_exception(self):
        embedder = AsyncMock()
        embedder.embed = AsyncMock(side_effect=Exception("embed 실패"))
        skill_search = AsyncMock()
        oc = _build_orchestrator(embedder=embedder, skill_search=skill_search, composer_state_store=AsyncMock())
        result = await oc._suggest_skill_select_node(_state())
        assert result["awaiting_skill_selection"] is False

    @pytest.mark.asyncio
    async def test_skill_without_node_definition_id_is_still_offered(self):
        """지침서형 스킬(node_definition_id=None)도 옵션에 노출 — 필터 제거 검증."""
        embedder = AsyncMock()
        embedder.embed = AsyncMock(return_value=[0.1] * 768)
        skill_search = AsyncMock()
        skill_search.execute_accessible = AsyncMock(return_value=[_skill(node_definition_id=None)])
        oc = _build_orchestrator(embedder=embedder, skill_search=skill_search, composer_state_store=AsyncMock())
        result = await oc._suggest_skill_select_node(_state())
        assert result["awaiting_skill_selection"] is True
        frames = [f for f in result["collected_frames"] if isinstance(f, SkillSelectionFrame)]
        assert frames[0].options[0].node_definition_id is None


# ---------------------------------------------------------------- resume


class TestResume:
    @pytest.mark.asyncio
    async def test_restores_state_from_store(self):
        node_id = uuid4()
        offered = uuid4()
        spec = DraftSpec(
            natural_language_intent="원래 요청",
            unresolved_nodes=[],
            discovered_entities={"a": 1},
            slot_filling_state=SlotFillingState(asked=[], pending=[], filled={}),
            consultant_turn_count=0,
        )
        st = _state(round=2)
        blob = {
            "user_id": str(st["user_id"]),  # 소유권 일치
            "offered_skill_ids": [str(offered)],
            "draft_spec": spec.model_dump(mode="json"),
            "node_candidates": [_node_config(node_id=node_id, category="ai").model_dump(mode="json")],
            "intent": "draft",
            "intent_analyzed_entities": {"a": 1},
        }
        store = AsyncMock()
        store.load_state = AsyncMock(return_value=blob)
        oc = _build_orchestrator(composer_state_store=store)

        result = await oc._resume_node(st)
        assert result["resume_ok"] is True
        assert result["draft_spec"].natural_language_intent == "원래 요청"
        assert len(result["node_candidates"]) == 1
        assert result["node_candidates"][0].node_id == node_id
        assert result["intent"] == "draft"
        assert result["offered_skill_ids"] == [str(offered)]

    @pytest.mark.asyncio
    async def test_rejects_when_owner_mismatch(self):
        """영속 user_id ≠ 호출자 → 거부 (세션 탈취 차단, MED #1)."""
        blob = {"user_id": str(uuid4()), "draft_spec": None, "node_candidates": []}  # 다른 소유자
        store = AsyncMock()
        store.load_state = AsyncMock(return_value=blob)
        oc = _build_orchestrator(composer_state_store=store)
        result = await oc._resume_node(_state(round=2))
        assert result["resume_ok"] is False
        errs = [f for f in result["collected_frames"] if isinstance(f, ErrorFrame)]
        assert errs and errs[0].code == "E_SESSION_EXPIRED"  # generic — 존재 누설 방지

    @pytest.mark.asyncio
    async def test_transient_load_error_distinguished_from_expiry(self):
        """일시적 저장소 오류는 E_RESUME_FAILED로 만료와 구분 (LOW #3)."""
        store = AsyncMock()
        store.load_state = AsyncMock(side_effect=Exception("GCS 503"))
        oc = _build_orchestrator(composer_state_store=store)
        result = await oc._resume_node(_state(round=2))
        assert result["resume_ok"] is False
        errs = [f for f in result["collected_frames"] if isinstance(f, ErrorFrame)]
        assert errs and errs[0].code == "E_RESUME_FAILED"

    @pytest.mark.asyncio
    async def test_session_expired_when_no_state(self):
        store = AsyncMock()
        store.load_state = AsyncMock(return_value=None)
        oc = _build_orchestrator(composer_state_store=store)
        result = await oc._resume_node(_state(round=2))
        assert result["resume_ok"] is False
        errs = [f for f in result["collected_frames"] if isinstance(f, ErrorFrame)]
        assert errs and errs[0].code == "E_SESSION_EXPIRED"

    @pytest.mark.asyncio
    async def test_session_expired_when_store_not_injected(self):
        oc = _build_orchestrator(composer_state_store=None)
        result = await oc._resume_node(_state(round=2))
        assert result["resume_ok"] is False
        errs = [f for f in result["collected_frames"] if isinstance(f, ErrorFrame)]
        assert errs and errs[0].code == "E_SESSION_EXPIRED"


# ---------------------------------------------------------------- bind_skill


class TestBindSkill:
    @pytest.mark.asyncio
    async def test_binds_skill_to_first_ai_node(self):
        sel = uuid4()
        ai_node_id = uuid4()
        plain_node_id = uuid4()
        wf = _workflow([_node_instance(plain_node_id), _node_instance(ai_node_id)])
        candidates = [
            _node_config(node_id=plain_node_id, category="trigger"),
            _node_config(node_id=ai_node_id, category="ai"),
        ]
        oc = _build_orchestrator()
        result = await oc._bind_skill_node(
            _state(
                selected_skill_id=sel,
                workflow_draft=wf,
                node_candidates=candidates,
                offered_skill_ids=[str(sel)],
            )
        )
        bound = result["workflow_draft"]
        # ai 노드만 skill_id 바인딩
        by_node = {n.node_id: n.skill_id for n in bound.nodes}
        assert by_node[ai_node_id] == sel
        assert by_node[plain_node_id] is None

    @pytest.mark.asyncio
    async def test_rejects_skill_id_not_in_offered_options(self):
        """제시 안 된 skill_id 바인딩 거부 — IDOR/스코프 우회 차단 (MED #1)."""
        offered = uuid4()
        attacker = uuid4()  # 제시되지 않은 임의 skill_id (타 스코프)
        ai_node_id = uuid4()
        wf = _workflow([_node_instance(ai_node_id)])
        candidates = [_node_config(node_id=ai_node_id, category="ai")]
        oc = _build_orchestrator()
        result = await oc._bind_skill_node(
            _state(
                selected_skill_id=attacker,
                workflow_draft=wf,
                node_candidates=candidates,
                offered_skill_ids=[str(offered)],
            )
        )
        # 바인딩 안 됨 — workflow_draft 미반환
        assert "workflow_draft" not in result
        assert result.get("collected_frames")

    @pytest.mark.asyncio
    async def test_noop_when_no_selection(self):
        wf = _workflow([_node_instance(uuid4())])
        oc = _build_orchestrator()
        result = await oc._bind_skill_node(_state(selected_skill_id=None, workflow_draft=wf))
        assert result == {}

    @pytest.mark.asyncio
    async def test_warns_when_no_ai_node(self):
        sel = uuid4()
        plain_id = uuid4()
        wf = _workflow([_node_instance(plain_id)])
        candidates = [_node_config(node_id=plain_id, category="trigger")]
        oc = _build_orchestrator()
        result = await oc._bind_skill_node(
            _state(selected_skill_id=sel, workflow_draft=wf, node_candidates=candidates, offered_skill_ids=[str(sel)])
        )
        # 바인딩 없음 — workflow_draft 미반환, 경고 frame만
        assert "workflow_draft" not in result
        assert result.get("collected_frames")

    @pytest.mark.asyncio
    async def test_falls_back_to_registry_for_category(self):
        """node_candidates에 없으면 registry로 category 조회."""
        sel = uuid4()
        ai_node_id = uuid4()
        wf = _workflow([_node_instance(ai_node_id)])
        oc = _build_orchestrator()
        oc._node_registry.get_schema = AsyncMock(return_value=_node_config(node_id=ai_node_id, category="ai"))
        result = await oc._bind_skill_node(
            _state(selected_skill_id=sel, workflow_draft=wf, node_candidates=[], offered_skill_ids=[str(sel)])
        )
        assert result["workflow_draft"].nodes[0].skill_id == sel


# ---------------------------------------------------------------- routers


class TestRouters:
    def test_route_entry(self):
        assert LangGraphOrchestrator._route_entry(_state(round=1)) == "compress"
        assert LangGraphOrchestrator._route_entry(_state(round=2)) == "resume"
        assert LangGraphOrchestrator._route_entry({}) == "compress"  # 기본 1차

    def test_route_after_resume(self):
        assert LangGraphOrchestrator._route_after_resume(_state(resume_ok=True)) == "draft"
        assert LangGraphOrchestrator._route_after_resume(_state(resume_ok=False)) == "end"

    def test_route_after_suggest(self):
        assert LangGraphOrchestrator._route_after_suggest(_state(awaiting_skill_selection=True)) == "wait"
        assert LangGraphOrchestrator._route_after_suggest(_state(awaiting_skill_selection=False)) == "draft"


# ---------------------------------------------------------------- serialize round-trip


class TestEndToEndStream:
    """oc.stream() 전체 astream 순회 — round 분기/중단/재개/바인딩 통합 검증."""

    @pytest.mark.asyncio
    async def test_round1_stops_at_skill_selection_without_drafting(self):
        from common_schemas.agent import IntentResult
        from common_schemas.enums import IntentType
        from nodes_graph.domain.services.graph_validator import GraphValidator

        intent_analyzer = AsyncMock(spec=IntentAnalyzerService)
        intent_analyzer.analyze = AsyncMock(
            return_value=IntentResult(intent=IntentType.DRAFT, confidence=0.9, analyzed_entities={})
        )
        drafter = AsyncMock(spec=DrafterService)
        node_registry = AsyncMock(spec=NodeRegistry)
        node_registry.search = AsyncMock(return_value=[_node_config(name="slack")])
        embedder = AsyncMock()
        embedder.embed = AsyncMock(return_value=[0.1] * 768)
        skill_search = AsyncMock()
        skill_search.execute_accessible = AsyncMock(return_value=[_skill(name="요약가")])
        store = AsyncMock()

        oc = LangGraphOrchestrator(
            intent_analyzer=intent_analyzer,
            drafter=drafter,
            qa_evaluator=AsyncMock(spec=QAEvaluatorService),
            slot_filler=SlotFillingService(),
            node_registry=node_registry,
            workflow_repo=AsyncMock(spec=WorkflowRepository),
            graph_validator=AsyncMock(spec=GraphValidator),
            embedder=embedder,
            skill_search=skill_search,
            composer_state_store=store,
        )

        frames = [f async for f in await oc.stream(uuid4(), uuid4(), "슬랙 알림 보내줘")]
        assert any(isinstance(f, SkillSelectionFrame) for f in frames)
        # 1차는 draft 미생성 — drafter 미호출 + 상태 영속됨
        drafter.draft.assert_not_called()
        store.save_state.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_round2_resumes_and_binds_skill_to_ai_node(self):
        from nodes_graph.domain.services.graph_validator import GraphValidator

        # 실제 _drafter_node 통과(node_type fix 포함) — resume→draft→bind→validate→qa→save 전구간.
        ai_node_id = uuid4()
        sel = uuid4()
        caller = uuid4()
        # 1차에서 영속됐을 상태 (소유자=caller, 제시 옵션에 sel 포함)
        spec = DraftSpec(
            natural_language_intent="슬랙 알림 보내줘",
            unresolved_nodes=[],
            discovered_entities={},
            slot_filling_state=SlotFillingState(asked=[], pending=[], filled={}),
            consultant_turn_count=0,
        )
        blob = {
            "user_id": str(caller),
            "offered_skill_ids": [str(sel)],
            "draft_spec": spec.model_dump(mode="json"),
            "node_candidates": [_node_config(node_id=ai_node_id, name="llm", category="ai").model_dump(mode="json")],
            "intent": "draft",
            "intent_analyzed_entities": {},
        }
        store = AsyncMock()
        store.load_state = AsyncMock(return_value=blob)

        drafted = _workflow([_node_instance(ai_node_id)])
        drafter = AsyncMock(spec=DrafterService)
        drafter.draft = AsyncMock(return_value=drafted)

        qa = AsyncMock(spec=QAEvaluatorService)
        qa.evaluate = AsyncMock(return_value=MagicMock(score=9.0, pass_flag=True, feedback="ok", reason="good"))

        validator = AsyncMock(spec=GraphValidator)
        validator.validate = AsyncMock(return_value=None)

        repo = AsyncMock(spec=WorkflowRepository)
        repo.save = AsyncMock(return_value=uuid4())

        oc = LangGraphOrchestrator(
            intent_analyzer=AsyncMock(spec=IntentAnalyzerService),
            drafter=drafter,
            qa_evaluator=qa,
            slot_filler=SlotFillingService(),
            node_registry=AsyncMock(spec=NodeRegistry),
            workflow_repo=repo,
            graph_validator=validator,
            composer_state_store=store,
        )

        async for _ in await oc.stream(caller, uuid4(), "", round=2, selected_skill_id=sel):
            pass
        # resume 호출 + draft 수행됨
        store.load_state.assert_awaited_once()
        drafter.draft.assert_awaited_once()
        # 저장된 워크플로우의 ai 노드에 skill_id 바인딩
        saved_workflow = repo.save.await_args.args[0]
        ai_nodes = [n for n in saved_workflow.nodes if n.node_id == ai_node_id]
        assert ai_nodes and ai_nodes[0].skill_id == sel
        # 2차 성공 종료 시 상태 정리
        store.delete_state.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_round2_session_expired_emits_error(self):
        from common_schemas.transport import ErrorFrame as _ErrorFrame
        from nodes_graph.domain.services.graph_validator import GraphValidator

        store = AsyncMock()
        store.load_state = AsyncMock(return_value=None)
        drafter = AsyncMock(spec=DrafterService)

        oc = LangGraphOrchestrator(
            intent_analyzer=AsyncMock(spec=IntentAnalyzerService),
            drafter=drafter,
            qa_evaluator=AsyncMock(spec=QAEvaluatorService),
            slot_filler=SlotFillingService(),
            node_registry=AsyncMock(spec=NodeRegistry),
            workflow_repo=AsyncMock(spec=WorkflowRepository),
            graph_validator=AsyncMock(spec=GraphValidator),
            composer_state_store=store,
        )

        frames = [f async for f in await oc.stream(uuid4(), uuid4(), "", round=2, selected_skill_id=uuid4())]
        errs = [f for f in frames if isinstance(f, _ErrorFrame) and f.code == "E_SESSION_EXPIRED"]
        assert errs
        drafter.draft.assert_not_called()


class TestSerializeResumeState:
    def test_round_trip(self):
        node_id = uuid4()
        offered = uuid4()
        st = _state(
            node_candidates=[_node_config(node_id=node_id, category="ai")],
            intent_analyzed_entities={"k": "v"},
        )
        blob = LangGraphOrchestrator._serialize_resume_state(st, [str(offered)])
        # JSON 직렬화 가능해야 함
        import json
        json.dumps(blob)
        assert blob["draft_spec"]["natural_language_intent"] == "슬랙 알림 보내줘"
        assert len(blob["node_candidates"]) == 1
        assert blob["intent_analyzed_entities"] == {"k": "v"}
        assert blob["user_id"] == str(st["user_id"])
        assert blob["offered_skill_ids"] == [str(offered)]

        # 복원
        restored = NodeConfig.model_validate(blob["node_candidates"][0])
        assert restored.node_id == node_id
        assert restored.category == "ai"


class TestEnsureLlmCandidate:
    """#372 결함 A — 스킬 바인딩 대상 LLM 노드(category=="ai")를 후보에 보장."""

    @pytest.mark.asyncio
    async def test_adds_llm_node_when_absent(self):
        oc = _build_orchestrator()
        oc._node_registry.search = AsyncMock(return_value=[_node_config(name="gemma_chat", category="ai")])
        out = await oc._ensure_llm_candidate([_node_config(name="email", category="action")])
        assert any(c.category == "ai" for c in out)
        assert len(out) == 2

    @pytest.mark.asyncio
    async def test_noop_when_search_has_no_ai_node(self):
        oc = _build_orchestrator()
        oc._node_registry.search = AsyncMock(return_value=[_node_config(name="x", category="action")])
        base = [_node_config(name="email", category="action")]
        assert await oc._ensure_llm_candidate(base) == base

    @pytest.mark.asyncio
    async def test_noop_on_search_failure(self):
        oc = _build_orchestrator()
        oc._node_registry.search = AsyncMock(side_effect=Exception("registry down"))
        base = [_node_config(name="email", category="action")]
        assert await oc._ensure_llm_candidate(base) == base


class TestDrafterNodeSkillBinding:
    """#372 결함 A — selected_skill_id가 있으면 drafter에 skill_selected=True + LLM 노드 보장."""

    @pytest.mark.asyncio
    async def test_passes_skill_selected_and_ensures_llm_candidate(self):
        oc = _build_orchestrator()
        oc._node_registry.search = AsyncMock(return_value=[_node_config(name="gemma_chat", category="ai")])
        oc._drafter.draft = AsyncMock(return_value=_workflow([]))

        await oc._drafter_node(_state(
            selected_skill_id=uuid4(),
            node_candidates=[_node_config(name="email", category="action")],
            qa_attempts=0,
        ))

        kwargs = oc._drafter.draft.call_args.kwargs
        assert kwargs["skill_selected"] is True
        passed_candidates = oc._drafter.draft.call_args.args[1]
        assert any(c.category == "ai" for c in passed_candidates)

    @pytest.mark.asyncio
    async def test_no_skill_selected_does_not_force_llm(self):
        oc = _build_orchestrator()
        oc._node_registry.search = AsyncMock(return_value=[_node_config(name="gemma_chat", category="ai")])
        oc._drafter.draft = AsyncMock(return_value=_workflow([]))

        await oc._drafter_node(_state(
            selected_skill_id=None,
            node_candidates=[_node_config(name="email", category="action")],
            qa_attempts=0,
        ))

        kwargs = oc._drafter.draft.call_args.kwargs
        assert kwargs["skill_selected"] is False
        # LLM 노드 강제 확보 안 함 (search로 LLM 노드 끌어오지 않음)
        passed_candidates = oc._drafter.draft.call_args.args[1]
        assert not any(c.category == "ai" for c in passed_candidates)

    @pytest.mark.asyncio
    async def test_no_ai_node_available_does_not_instruct_binding(self):
        """LLM 노드 확보 실패(카탈로그에 ai 노드 미검출) 시 drafter에 바인딩 지시 안 함 (#376 LOW #2)."""
        oc = _build_orchestrator()
        oc._node_registry.search = AsyncMock(return_value=[_node_config(name="x", category="action")])
        oc._drafter.draft = AsyncMock(return_value=_workflow([]))

        await oc._drafter_node(_state(
            selected_skill_id=uuid4(),
            node_candidates=[_node_config(name="email", category="action")],
            qa_attempts=0,
        ))

        # 후보에 ai 노드가 없으므로 skill_selected=False로 전달(지시/후보 desync 방지)
        assert oc._drafter.draft.call_args.kwargs["skill_selected"] is False
