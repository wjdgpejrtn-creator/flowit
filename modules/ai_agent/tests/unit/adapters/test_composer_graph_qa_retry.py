"""_qa_retry_node 단위 테스트 — #378 후속 B: 재시도 시 retriever 재검색으로 후보 갱신.

직전 후보로 충족 못 한 능력(QA가 feedback에 적은 missing_capabilities)을 쿼리에 보강해
새 노드를 끌어온다. 기존 후보는 보존하고 합집합(node_id dedup) — 직전에 쓰던 노드를
잃지 않게. 재검색 실패는 비치명적(retry_feedback는 그대로 설정).
"""
from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from common_schemas.agent import DraftSpec, SlotFillingState
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
        node_type=name,
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


def _orchestrator(search_result):
    from nodes_graph.domain.services.graph_validator import GraphValidator

    node_registry = AsyncMock(spec=NodeRegistry)
    node_registry.search = AsyncMock(return_value=search_result)
    node_registry.list_structural = AsyncMock(return_value=[])
    return LangGraphOrchestrator(
        intent_analyzer=AsyncMock(spec=IntentAnalyzerService),
        drafter=AsyncMock(spec=DrafterService),
        qa_evaluator=AsyncMock(spec=QAEvaluatorService),
        slot_filler=SlotFillingService(),
        node_registry=node_registry,
        workflow_repo=AsyncMock(spec=WorkflowRepository),
        graph_validator=AsyncMock(spec=GraphValidator),
    )


def _state(existing_candidates, feedback="누락된 필수 노드/채널: 이메일 발송", dropped=None):
    return {
        "session_id": uuid4(),
        "user_id": uuid4(),
        "draft_spec": DraftSpec(
            natural_language_intent="광고 시트 읽어서 요약해 알림",
            unresolved_nodes=[],
            discovered_entities={},
            slot_filling_state=SlotFillingState(asked=[], pending=[], filled={}),
            consultant_turn_count=0,
        ),
        "node_candidates": existing_candidates,
        "qa_feedback": feedback,
        "validation_issues": None,
        "dropped_node_types": dropped or [],
        "qa_attempts": 1,
        "retry_count": 0,
    }


class TestQARetryReSearch:
    @pytest.mark.asyncio
    async def test_sets_retry_feedback(self):
        """기존 동작 보존 — qa_feedback/validation_issues를 retry_feedback으로 합친다."""
        oc = _orchestrator(search_result=[])
        result = await oc._qa_retry_node(_state(existing_candidates=[]))
        assert "이메일 발송" in result["retry_feedback"]
        assert result["retry_count"] == 1

    @pytest.mark.asyncio
    async def test_research_merges_new_candidates(self):
        """재검색이 끌어온 새 노드가 기존 후보에 합쳐진다(union)."""
        existing = _node_config(name="google_sheets_read")
        fresh = _node_config(name="email_send")
        oc = _orchestrator(search_result=[fresh])

        result = await oc._qa_retry_node(_state(existing_candidates=[existing]))

        names = {c.name for c in result["node_candidates"]}
        assert names == {"google_sheets_read", "email_send"}

    @pytest.mark.asyncio
    async def test_research_query_includes_feedback(self):
        """재검색 쿼리에 missing_capabilities(피드백)가 보강돼 들어간다."""
        oc = _orchestrator(search_result=[])
        await oc._qa_retry_node(_state(existing_candidates=[], feedback="누락: 이메일 발송"))

        oc._node_registry.search.assert_called_once()
        (query,), _ = oc._node_registry.search.call_args
        assert "이메일 발송" in query
        assert "광고 시트" in query  # 원 intent도 포함

    @pytest.mark.asyncio
    async def test_research_query_includes_dropped_node_types(self):
        """drafter가 버린 node_type(ground-truth)이 재검색 쿼리에 직접 들어간다 — QA-LLM
        재인지에 의존하지 않고 결정적으로 그 노드를 재검색(#378 후속 리뷰 #2)."""
        oc = _orchestrator(search_result=[])
        await oc._qa_retry_node(
            _state(existing_candidates=[], feedback="", dropped=["email_send"])
        )

        oc._node_registry.search.assert_called_once()
        (query,), _ = oc._node_registry.search.call_args
        assert "email_send" in query

    @pytest.mark.asyncio
    async def test_research_dedup_no_duplicate(self):
        """재검색이 기존 + 같은 node_id(dup)를 돌려줘도 합집합에 중복이 안 생긴다."""
        shared = uuid4()
        fresh_id = uuid4()
        existing = _node_config(node_id=shared, name="google_sheets_read")
        dup = _node_config(node_id=shared, name="google_sheets_read")
        new = _node_config(node_id=fresh_id, name="email_send")
        oc = _orchestrator(search_result=[dup, new])

        result = await oc._qa_retry_node(_state(existing_candidates=[existing]))

        ids = [c.node_id for c in result["node_candidates"]]
        assert ids.count(shared) == 1
        assert fresh_id in ids

    @pytest.mark.asyncio
    async def test_research_all_dup_leaves_candidates_unchanged(self):
        """재검색이 전부 기존과 겹치면(신규 0) node_candidates를 갱신하지 않는다(no-op)."""
        shared = uuid4()
        existing = _node_config(node_id=shared, name="google_sheets_read")
        dup = _node_config(node_id=shared, name="google_sheets_read")
        oc = _orchestrator(search_result=[dup])

        result = await oc._qa_retry_node(_state(existing_candidates=[existing]))

        # 신규 후보가 없으므로 불필요한 state 갱신을 피한다 — 키 부재 또는 동일 유지
        assert "node_candidates" not in result

    @pytest.mark.asyncio
    async def test_research_failure_is_non_fatal(self):
        """재검색 실패해도 retry_feedback은 정상 설정, 기존 후보 보존."""
        existing = _node_config(name="google_sheets_read")
        oc = _orchestrator(search_result=[])
        oc._node_registry.search = AsyncMock(side_effect=Exception("embed 오류"))

        result = await oc._qa_retry_node(_state(existing_candidates=[existing]))

        assert result["retry_feedback"]
        # node_candidates는 갱신 안 됐거나(키 없음) 기존 그대로
        if "node_candidates" in result:
            names = {c.name for c in result["node_candidates"]}
            assert names == {"google_sheets_read"}


class TestNoProgressRetryGuard:
    """재시도 무한 헛바퀴 차단 — draft가 직전과 동일하면(결정적 스켈레톤 재조립 / LLM invent→drop
    동일 불완전) 재시도 여력이 남아도 즉시 종결. out-of-scope(없는 노드 필요) 요청 빠른 실패."""

    def test_qa_promotes_on_pass(self):
        assert LangGraphOrchestrator._route_after_qa({"pass_flag": True}) == "promote"

    def test_qa_fails_fast_when_draft_repeated(self):
        # qa_attempts=0 (여력 충분)인데도 draft_repeated면 retry_draft 아닌 qa_failed.
        s = {"pass_flag": False, "draft_repeated": True, "qa_attempts": 0}
        assert LangGraphOrchestrator._route_after_qa(s) == "qa_failed"

    def test_qa_retries_when_progress(self):
        s = {"pass_flag": False, "draft_repeated": False, "qa_attempts": 0}
        assert LangGraphOrchestrator._route_after_qa(s) == "retry_draft"

    def test_validate_fails_fast_when_draft_repeated(self):
        s = {"pass_flag": False, "draft_repeated": True, "retry_count": 0}
        assert LangGraphOrchestrator._route_after_validate(s) == "validation_failed"

    def test_validate_retries_when_progress(self):
        s = {"pass_flag": False, "draft_repeated": False, "retry_count": 0}
        assert LangGraphOrchestrator._route_after_validate(s) == "retry_draft"


class TestDraftSignature:
    """구조 시그니처 — instance_id(매 draft 랜덤) 무관하게 node_id 구조만 비교."""

    @staticmethod
    def _wf(node_ids, edges):
        from common_schemas.workflow import Edge, NodeInstance, Position, WorkflowSchema

        insts = [
            NodeInstance(instance_id=uuid4(), node_id=nid, parameters={}, position=Position(x=0.0, y=0.0))
            for nid in node_ids
        ]
        conns = [
            Edge(
                from_instance_id=insts[a].instance_id, to_instance_id=insts[b].instance_id,
                from_handle="output", to_handle="input",
            )
            for a, b in edges
        ]
        return WorkflowSchema(
            workflow_id=uuid4(), name="t", scope="private", is_draft=True,
            nodes=insts, connections=conns, owner_user_id=uuid4(),
        )

    def test_identical_structure_same_signature(self):
        n1, n2 = uuid4(), uuid4()
        # 같은 node_id 구성 + 같은 엣지, instance_id만 다름 → 시그니처 동일.
        a = self._wf([n1, n2], [(0, 1)])
        b = self._wf([n1, n2], [(0, 1)])
        assert LangGraphOrchestrator._draft_signature(a) == LangGraphOrchestrator._draft_signature(b)

    def test_different_nodes_different_signature(self):
        n1, n2, n3 = uuid4(), uuid4(), uuid4()
        a = self._wf([n1, n2], [(0, 1)])
        b = self._wf([n1, n3], [(0, 1)])
        assert LangGraphOrchestrator._draft_signature(a) != LangGraphOrchestrator._draft_signature(b)
