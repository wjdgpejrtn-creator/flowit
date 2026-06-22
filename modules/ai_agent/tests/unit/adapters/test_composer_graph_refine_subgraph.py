"""refine 전용 서브그래프 (op 기반 편집) — 라우팅 + plan/apply 노드 + 확인 리포트 (PR-2)."""
from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from common_schemas import NodeConfig, NodeInstance, Position, WorkflowSchema
from common_schemas.agent import DraftSpec, SlotFillingState
from common_schemas.enums import RiskLevel

from ai_agent.adapters.langgraph.composer_graph import LangGraphOrchestrator
from ai_agent.domain.ports.node_registry import NodeRegistry
from ai_agent.domain.ports.workflow_repository import WorkflowRepository
from ai_agent.domain.services import (
    DrafterService,
    IntentAnalyzerService,
    QAEvaluatorService,
    SlotFillingService,
    WorkflowEditPlanner,
    WorkflowEditService,
)
from ai_agent.domain.services.workflow_edit_service import (
    EditPlan,
    ReplaceNodeOp,
    SetParamOp,
)


def _cfg(node_type: str, node_id=None) -> NodeConfig:
    return NodeConfig(
        node_id=node_id or uuid4(), node_type=node_type, name=node_type, category="test",
        version="1.0", input_schema={}, output_schema={}, parameter_schema={},
        risk_level=RiskLevel.LOW, required_connections=[], description="", is_mvp=True,
    )


def _wf(nodes, edges=None) -> WorkflowSchema:
    return WorkflowSchema(
        workflow_id=uuid4(), name="WF", scope="private", is_draft=False,
        owner_user_id=uuid4(), nodes=nodes, connections=edges or [],
    )


def _node(cfg: NodeConfig, params=None) -> NodeInstance:
    return NodeInstance(instance_id=uuid4(), node_id=cfg.node_id, parameters=params or {},
                        position=Position(x=0, y=0))


def _orch(*, draft_store=None, planner=None) -> LangGraphOrchestrator:
    from nodes_graph.domain.services.graph_validator import GraphValidator
    nr = AsyncMock(spec=NodeRegistry)
    nr.search = AsyncMock(return_value=[])
    return LangGraphOrchestrator(
        intent_analyzer=AsyncMock(spec=IntentAnalyzerService),
        drafter=AsyncMock(spec=DrafterService),
        qa_evaluator=AsyncMock(spec=QAEvaluatorService),
        slot_filler=SlotFillingService(),
        node_registry=nr,
        workflow_repo=AsyncMock(spec=WorkflowRepository),
        graph_validator=AsyncMock(spec=GraphValidator),
        workflow_draft_store=draft_store,
        workflow_edit_planner=planner,
        workflow_edit_service=WorkflowEditService(),
    )


def _state(prior, candidates, *, msg="slack말고 gmail로 변경해줘", **extra) -> dict:
    base = {
        "session_id": uuid4(), "user_id": uuid4(), "user_role": "User", "department_id": None,
        "messages": [{"role": "user", "content": msg}], "turn_count": 2, "personal_memory": [],
        "personal_patterns": [], "intent": "refine", "intent_analyzed_entities": {},
        "draft_spec": DraftSpec(natural_language_intent=msg, unresolved_nodes=[], discovered_entities={},
                                slot_filling_state=SlotFillingState(asked=[], pending=[], filled={}),
                                consultant_turn_count=0),
        "node_candidates": candidates, "loaded_prior_workflow": prior, "workflow_draft": None,
        "qa_attempts": 0, "qa_score": 0.0, "pass_flag": False, "qa_feedback": "",
        "retry_feedback": "", "validation_issues": None, "collected_frames": [], "error": None,
        "refine_plan_attempts": 0, "edit_plan": None, "edit_fallback": False, "refine_route": None,
    }
    base.update(extra)
    return base


# ── 라우팅 ────────────────────────────────────────────────────────────────────
class TestRouting:
    def test_suggest_routes_refine_to_plan(self):
        assert LangGraphOrchestrator._route_after_suggest({"intent": "refine"}) == "refine"
        assert LangGraphOrchestrator._route_after_suggest({"intent": "draft"}) == "draft"
        assert LangGraphOrchestrator._route_after_suggest({"awaiting_skill_selection": True}) == "wait"

    def test_validate_refine_pass_skips_qa_goes_promote(self):
        assert LangGraphOrchestrator._route_after_validate({"intent": "refine", "pass_flag": True}) == "promote"

    def test_validate_refine_fail_replans_then_fails(self):
        assert LangGraphOrchestrator._route_after_validate(
            {"intent": "refine", "pass_flag": False, "refine_plan_attempts": 1}) == "refine_plan"
        assert LangGraphOrchestrator._route_after_validate(
            {"intent": "refine", "pass_flag": False, "refine_plan_attempts": 2}) == "validation_failed"

    def test_validate_fresh_path_unchanged(self):
        assert LangGraphOrchestrator._route_after_validate({"intent": "draft", "pass_flag": True}) == "qa_evaluator"

    def test_route_after_refine_plan(self):
        assert LangGraphOrchestrator._route_after_refine_plan({"error": "x"}) == "end"
        assert LangGraphOrchestrator._route_after_refine_plan({"refine_route": "replan"}) == "replan"
        assert LangGraphOrchestrator._route_after_refine_plan({"refine_route": "apply"}) == "apply"


# ── _refine_plan_node ─────────────────────────────────────────────────────────
class TestRefinePlanNode:
    @pytest.mark.asyncio
    async def test_prior_missing_errors_never_fresh(self):
        orch = _orch(draft_store=None, planner=AsyncMock(spec=WorkflowEditPlanner))
        out = await orch._refine_plan_node(_state(None, []))
        assert "찾지 못했" in out["error"]

    @pytest.mark.asyncio
    async def test_good_plan_routes_apply(self):
        slack, gmail = _cfg("slack_post_message"), _cfg("gmail_send")
        prior = _wf([_node(slack)])
        planner = AsyncMock(spec=WorkflowEditPlanner)
        planner.plan = AsyncMock(return_value=EditPlan(ops=[
            ReplaceNodeOp(op="replace_node", target_ref="n0", new_node_type="gmail_send")]))
        orch = _orch(planner=planner)
        orch._node_registry.get_schema = AsyncMock(return_value=gmail)  # augment 복원
        out = await orch._refine_plan_node(_state(prior, [slack, gmail]))
        assert out["refine_route"] == "apply"
        assert out["edit_plan"] is not None

    @pytest.mark.asyncio
    async def test_planner_none_falls_back(self):
        slack = _cfg("slack_post_message")
        prior = _wf([_node(slack)])
        orch = _orch(planner=None)  # llm 미주입 → planner None
        out = await orch._refine_plan_node(_state(prior, [slack]))
        assert out["edit_fallback"] is True and out["refine_route"] == "apply"

    @pytest.mark.asyncio
    async def test_bad_node_type_replans_then_falls_back(self):
        slack = _cfg("slack_post_message")
        prior = _wf([_node(slack)])
        planner = AsyncMock(spec=WorkflowEditPlanner)
        planner.plan = AsyncMock(return_value=EditPlan(ops=[
            ReplaceNodeOp(op="replace_node", target_ref="n0", new_node_type="ghost_node")]))
        orch = _orch(planner=planner)
        # 1차: 불량 type, 시도 남음 → replan
        out1 = await orch._refine_plan_node(_state(prior, [slack], refine_plan_attempts=0))
        assert out1["refine_route"] == "replan" and out1["refine_plan_attempts"] == 1
        # 2차(소진): → drafter 폴백
        out2 = await orch._refine_plan_node(_state(prior, [slack], refine_plan_attempts=1))
        assert out2["edit_fallback"] is True and out2["refine_route"] == "apply"


# ── _refine_apply_node ────────────────────────────────────────────────────────
class TestRefineApplyNode:
    @pytest.mark.asyncio
    async def test_applies_plan_deterministically(self):
        slack, gmail = _cfg("slack_post_message"), _cfg("gmail_send")
        n0 = _node(slack, {"channel": "#general"})
        prior = _wf([n0])
        orch = _orch()
        plan = EditPlan(ops=[ReplaceNodeOp(op="replace_node", target_ref="n0", new_node_type="gmail_send",
                                           parameters={"to": "a@b"})])
        out = await orch._refine_apply_node(_state(prior, [slack, gmail], edit_plan=plan))
        wf = out["workflow_draft"]
        assert out["edit_fallback"] is False
        # 같은 instance_id 유지 + node_id가 gmail로 교체
        repl = next(n for n in wf.nodes if n.instance_id == n0.instance_id)
        assert repl.node_id == gmail.node_id
        orch._drafter.draft.assert_not_awaited()  # drafter 폴백 미사용

    @pytest.mark.asyncio
    async def test_no_plan_falls_back_to_drafter(self):
        slack = _cfg("slack_post_message")
        prior = _wf([_node(slack)])
        orch = _orch()
        orch._drafter.draft = AsyncMock(return_value=prior)
        out = await orch._refine_apply_node(_state(prior, [slack], edit_plan=None, edit_fallback=True))
        assert out["edit_fallback"] is True
        orch._drafter.draft.assert_awaited_once()
        assert out["workflow_draft"] is not None

    @pytest.mark.asyncio
    async def test_apply_exception_falls_back_to_drafter(self):
        slack = _cfg("slack_post_message")
        prior = _wf([_node(slack)])
        orch = _orch()
        orch._drafter.draft = AsyncMock(return_value=prior)
        # 존재하지 않는 ref를 가리키는 plan → applier가 E_REFINE_BAD_REF → drafter 폴백.
        plan = EditPlan(ops=[SetParamOp(op="set_param", target_ref="n9", parameters={"k": "v"})])
        out = await orch._refine_apply_node(_state(prior, [slack], edit_plan=plan))
        assert out["edit_fallback"] is True
        orch._drafter.draft.assert_awaited_once()


# ── 확인 리포트 ───────────────────────────────────────────────────────────────
class TestConfirmReport:
    def test_refine_report_shows_diff_not_qa(self):
        slack, gmail = _cfg("slack_post_message"), _cfg("gmail_send")
        n0 = _node(slack, {"channel": "#general"})
        prior = _wf([n0])
        # 편집 결과: 같은 instance_id, gmail로 교체
        final = _wf([n0.model_copy(update={"node_id": gmail.node_id})])
        report = LangGraphOrchestrator._build_qa_checklist(
            _state(prior, [slack, gmail], workflow_draft=final, intent="refine")
        )
        assert "수정 적용 완료" in report
        assert "QA 품질 평가" not in report

    def test_fresh_report_still_shows_qa(self):
        cfg = _cfg("http")
        wf = _wf([_node(cfg)])
        report = LangGraphOrchestrator._build_qa_checklist(
            _state(None, [cfg], workflow_draft=wf, intent="draft", qa_score=9.0)
        )
        assert "QA 품질 평가 통과" in report
