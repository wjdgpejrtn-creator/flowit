"""two-shot 풀체인 relay e2e — supervisor ↔ composer round-trip (REQ-013).

외부 경계(Modal LLM·GCS·DB·nodes_graph)만 페이크로 두고 **실제 코드 전 구간**을 구동한다:
  LangGraphSupervisor._run → _relay_stream(payload round/selected_skill_id)
    → composer SubAgentClient(agent-composer/main.py route 핸들러 충실 모사)
    → 실제 LangGraphOrchestrator(composer graph) round 분기

검증 초점 = 계획서 #1 위험 **payload relay 누락**(round/selected_skill_id가 supervisor
→composer hop을 건너 보존되는지) + 1차→2차 ComposerStateStore round-trip(JSON 직렬화 포함).
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from common_schemas.agent import IntentResult
from common_schemas.agent_protocol import AgentProtocolRequest, AgentProtocolResponse
from common_schemas.enums import IntentType, RiskLevel
from common_schemas.transport import ResultFrame, SkillSelectionFrame, WorkflowDraftFrame
from common_schemas.workflow import NodeConfig, NodeInstance, Position, WorkflowSchema

from ai_agent.adapters.langgraph.composer_graph import LangGraphOrchestrator
from ai_agent.adapters.supervisor import LangGraphSupervisor
from ai_agent.domain.ports.composer_state_store import ComposerStateStore
from ai_agent.domain.ports.node_registry import NodeRegistry
from ai_agent.domain.ports.sub_agent_client import SubAgentClient
from ai_agent.domain.ports.workflow_repository import WorkflowRepository
from ai_agent.domain.services import (
    DrafterService,
    IntentAnalyzerService,
    QAEvaluatorService,
    SlotFillingService,
)

# ---------------------------------------------------------------- fakes


class _MemComposerStateStore(ComposerStateStore):
    """GCS 대체 — 단, save 시 GCS와 동일하게 JSON(default=str) round-trip을 거쳐
    UUID→str 직렬화 손실이 resume의 model_validate에서 깨지지 않는지 함께 검증."""

    def __init__(self) -> None:
        self.blobs: dict[str, dict] = {}

    async def save_state(self, session_id, state):
        self.blobs[str(session_id)] = json.loads(json.dumps(state, ensure_ascii=False, default=str))

    async def load_state(self, session_id):
        return self.blobs.get(str(session_id))

    async def delete_state(self, session_id):
        self.blobs.pop(str(session_id), None)


class _ComposerBridge(SubAgentClient):
    """agent-composer/main.py route 핸들러를 인프로세스로 충실히 모사.

    payload에서 round/selected_skill_id를 꺼내 실제 composer.stream에 전달하고,
    프레임을 AgentProtocolResponse(next_action=continue)로 감싸 yield."""

    def __init__(self, composer: LangGraphOrchestrator) -> None:
        self._composer = composer

    async def send(self, request: AgentProtocolRequest):
        async for frame in await self._composer.stream(
            user_id=request.user_id,
            session_id=request.session_id,
            message=request.payload.get("message", ""),
            personal_memory=list(request.personal_memory),
            round=request.payload.get("round", 1),
            selected_skill_id=request.payload.get("selected_skill_id"),
        ):
            yield AgentProtocolResponse(frames=[frame], state_delta={}, next_action="continue")
        yield AgentProtocolResponse(frames=[], state_delta={}, next_action="complete")


class _NoopClient(SubAgentClient):
    """personalization/skills 스텁 — load_memory/update_memory no-op."""

    async def send(self, request: AgentProtocolRequest):
        yield AgentProtocolResponse(frames=[], state_delta={}, next_action="complete")


# ---------------------------------------------------------------- builders


def _node_config(node_id, category, name) -> NodeConfig:
    return NodeConfig(
        node_id=node_id, node_type=f"{name}_type", name=name, category=category, version="1.0.0",
        input_schema={}, output_schema={}, parameter_schema={}, risk_level=RiskLevel.LOW,
        required_connections=[], description=name, is_mvp=True,
    )


def _build_composer(store, ai_node_id, skill_id, intent=IntentType.DRAFT):
    """round 1 검색→옵션, round 2 resume→draft(ai 노드)→bind 가능한 composer.

    intent를 REFINE으로 주면 composer intent_node가 편집으로 분류 → suggest_skill_select
    게이트가 작동하는지(스킬 제안 우회) 검증할 수 있다(#369 후속)."""
    from nodes_graph.domain.services.graph_validator import GraphValidator

    trigger_id = uuid4()
    # node_registry.search → ai 노드 포함 후보 (round 1에 영속되어 round 2 bind의 category 출처)
    candidates = [_node_config(trigger_id, "trigger", "slack"), _node_config(ai_node_id, "ai", "llm")]
    node_registry = AsyncMock(spec=NodeRegistry)
    node_registry.search = AsyncMock(return_value=candidates)

    embedder = AsyncMock()
    embedder.embed = AsyncMock(return_value=[0.1] * 768)

    # skill_search → skill_id 1개 (옵션으로 제시 + round 2 selected가 이 값이어야 bind 허용)
    skill = MagicMock()
    skill.skill_id = skill_id
    skill.name = "요약 전문가"
    skill.description = "문서 요약 도메인 지침서"
    skill.node_definition_id = None
    skill_search = AsyncMock()
    skill_search.execute_accessible = AsyncMock(return_value=[skill])

    # drafter → ai 노드를 포함한 워크플로우 (bind 대상)
    drafted = WorkflowSchema(
        workflow_id=uuid4(), owner_user_id=uuid4(), name="wf", description=None, scope="private",
        is_draft=True,
        nodes=[
            NodeInstance(instance_id=uuid4(), node_id=trigger_id, parameters={}, position=Position(x=0, y=0)),
            NodeInstance(instance_id=uuid4(), node_id=ai_node_id, parameters={}, position=Position(x=1, y=0)),
        ],
        connections=[],
    )
    drafter = AsyncMock(spec=DrafterService)
    drafter.draft = AsyncMock(return_value=drafted)

    qa = AsyncMock(spec=QAEvaluatorService)
    qa.evaluate = AsyncMock(return_value=MagicMock(score=9.0, pass_flag=True, feedback="ok", reason="good"))

    validator = AsyncMock(spec=GraphValidator)
    validator.validate = AsyncMock(return_value=None)

    repo = AsyncMock(spec=WorkflowRepository)
    repo.save = AsyncMock(return_value=uuid4())

    # composer 내부 intent_node 분류 — DRAFT면 search_nodes→suggest_skill_select 도달,
    # REFINE이면 suggest_skill_select 게이트가 우회시켜 바로 draft로 가야 한다(#369).
    composer_intent = AsyncMock(spec=IntentAnalyzerService)
    composer_intent.analyze = AsyncMock(
        return_value=IntentResult(intent=intent, confidence=0.9, analyzed_entities={})
    )

    composer = LangGraphOrchestrator(
        intent_analyzer=composer_intent,
        drafter=drafter,
        qa_evaluator=qa,
        slot_filler=SlotFillingService(),
        node_registry=node_registry,
        workflow_repo=repo,
        graph_validator=validator,
        embedder=embedder,
        skill_search=skill_search,
        composer_state_store=store,
    )
    return composer, repo


def _build_supervisor(composer):
    intent_analyzer = AsyncMock(spec=IntentAnalyzerService)
    intent_analyzer.analyze = AsyncMock(
        return_value=IntentResult(intent=IntentType.DRAFT, confidence=0.9, analyzed_entities={})
    )
    return LangGraphSupervisor(
        intent_analyzer=intent_analyzer,
        personalization_client=_NoopClient(),
        composer_client=_ComposerBridge(composer),
        skills_client=_NoopClient(),
    )


# ---------------------------------------------------------------- e2e


class TestTwoShotRelayE2E:
    @pytest.mark.asyncio
    async def test_full_round_trip_binds_selected_skill(self):
        store = _MemComposerStateStore()
        ai_node_id = uuid4()
        skill_id = uuid4()
        composer, repo = _build_composer(store, ai_node_id, skill_id)
        supervisor = _build_supervisor(composer)

        user_id, session_id = uuid4(), uuid4()

        # ── 1차: 메시지 → supervisor → composer relay → SkillSelectionFrame ──
        r1 = [f async for f in await supervisor.stream(user_id, session_id, "슬랙 알림 보내줘")]
        selection = [f for f in r1 if isinstance(f, SkillSelectionFrame)]
        assert selection, "1차에서 SkillSelectionFrame이 supervisor relay로 전파돼야 함"
        offered = selection[0].options
        assert any(o.skill_id == skill_id for o in offered)
        # 1차는 draft 미생성(워크플로우 프레임 없음) — 옵션 제시 후 중단
        assert not [f for f in r1 if isinstance(f, WorkflowDraftFrame)]
        # 상태 영속됨 (round 2 재료)
        assert str(session_id) in store.blobs
        assert skill_id is not None

        # ── 2차: round=2 + 선택 skill_id → supervisor 직행 relay → resume→draft→bind ──
        r2 = [
            f async for f in await supervisor.stream(
                user_id, session_id, "", round=2, selected_skill_id=str(skill_id)
            )
        ]
        # 2차에는 워크플로우 초안 + 최종 결과 프레임
        assert [f for f in r2 if isinstance(f, WorkflowDraftFrame)], "2차에서 draft 생성돼야 함"
        assert [f for f in r2 if isinstance(f, ResultFrame)]

        # 핵심: 저장된 워크플로우의 ai 노드에 선택 skill_id 바인딩 (relay round-trip 성공 증명)
        repo.save.assert_awaited()
        saved = repo.save.await_args.args[0]
        ai_nodes = [n for n in saved.nodes if n.node_id == ai_node_id]
        assert ai_nodes and ai_nodes[0].skill_id == skill_id
        # 2차 성공 종료 → 상태 정리됨
        assert str(session_id) not in store.blobs

    @pytest.mark.asyncio
    async def test_refine_skips_skill_selection_and_drafts_in_one_round(self):
        """#369: refine(편집)은 two-shot 스킬 제안을 우회하고 한 라운드에 바로 draft한다.

        실제 composer 그래프를 supervisor relay로 전 구간 구동(외부만 페이크) — 재배포 없이
        '수정 발화가 스킬 카드로 끊겨 새 생성처럼 보이던' 회귀를 코드로 고정한다.
        """
        store = _MemComposerStateStore()
        ai_node_id, skill_id = uuid4(), uuid4()
        composer, repo = _build_composer(store, ai_node_id, skill_id, intent=IntentType.REFINE)
        supervisor = _build_supervisor(composer)
        user_id, session_id = uuid4(), uuid4()

        frames = [
            f async for f in await supervisor.stream(
                user_id, session_id, "이거 slack 말고 gmail로 보내는 것으로 수정해줘"
            )
        ]

        # 게이트 작동: 스킬 선택 카드가 뜨지 않아야 한다(편집은 스킬 제안 대상 아님).
        assert not [f for f in frames if isinstance(f, SkillSelectionFrame)], (
            "refine은 SkillSelectionFrame을 띄우면 안 됨 — 새 생성처럼 끊기던 버그"
        )
        # 같은 라운드에서 곧장 draft까지 진행(중단 없음).
        assert [f for f in frames if isinstance(f, WorkflowDraftFrame)], "refine은 한 라운드에 draft돼야 함"
        assert [f for f in frames if isinstance(f, ResultFrame)]
        # round 2 재료를 영속하지 않았다(중단 없이 완주).
        assert str(session_id) not in store.blobs

    @pytest.mark.asyncio
    async def test_round2_rejects_skill_not_offered(self):
        """relay로 도착한 임의 skill_id(미제시)는 bind에서 거부 — IDOR 차단 (전 구간)."""
        store = _MemComposerStateStore()
        ai_node_id = uuid4()
        offered_skill_id = uuid4()
        composer, repo = _build_composer(store, ai_node_id, offered_skill_id)
        supervisor = _build_supervisor(composer)
        user_id, session_id = uuid4(), uuid4()

        # 1차 (옵션 제시 + 영속)
        await _drain(supervisor.stream(user_id, session_id, "슬랙 알림 보내줘"))

        # 2차에 제시 안 된 임의 skill_id 주입
        attacker_skill = uuid4()
        await _drain(supervisor.stream(user_id, session_id, "", round=2, selected_skill_id=str(attacker_skill)))

        saved = repo.save.await_args.args[0]
        ai_nodes = [n for n in saved.nodes if n.node_id == ai_node_id]
        # 미제시 skill_id는 바인딩되지 않음 (None 유지)
        assert ai_nodes and ai_nodes[0].skill_id is None

    @pytest.mark.asyncio
    async def test_round2_owner_mismatch_blocks_resume(self):
        """다른 user_id가 같은 session_id로 2차 시도 → resume 거부(세션 탈취 차단)."""
        store = _MemComposerStateStore()
        composer, repo = _build_composer(store, uuid4(), uuid4())
        supervisor = _build_supervisor(composer)
        owner, session_id = uuid4(), uuid4()

        await _drain(supervisor.stream(owner, session_id, "슬랙 알림 보내줘"))
        skill_id = store.blobs[str(session_id)]["offered_skill_ids"][0]

        attacker = uuid4()
        await _drain(supervisor.stream(attacker, session_id, "", round=2, selected_skill_id=skill_id))

        # 소유권 불일치 → draft/save 미도달
        repo.save.assert_not_awaited()


async def _drain(coro):
    async for _ in await coro:
        pass
