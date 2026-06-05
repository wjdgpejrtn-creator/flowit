"""LangGraphSupervisor 제어 루프 단위 테스트 (P1).

langgraph(composer_graph) 의존 없이 fake SubAgentClient/IntentAnalyzer로 루프
자체를 구동한다. 검증 초점 = 1-홉 디스패처 → 루프 셸 승격 시 **프레임 시퀀스
회귀 0** (어떤 AgentNodeFrame/transition이 yield되는지, relay 후 update_memory).

설계: docs/specs/plan/supervisor-loop-architecture.md §9 Phase P1.
"""
from __future__ import annotations

from uuid import uuid4

import pytest
from common_schemas.agent import IntentResult
from common_schemas.agent_protocol import AgentProtocolResponse
from common_schemas.enums import IntentType
from common_schemas.transport import (
    AgentNodeFrame,
    ChatMessageFrame,
    ErrorFrame,
    ResultFrame,
    SessionFrame,
    WorkflowDraftFrame,
)

from ai_agent.adapters.supervisor import LangGraphSupervisor
from ai_agent.domain.ports.sub_agent_client import SubAgentClient

# ---------------------------------------------------------------- fakes


class _FakeClient(SubAgentClient):
    """프레임 시퀀스를 그대로 흘려보내는 fake sub-agent. 호출 payload를 기록."""

    def __init__(self, frames: list | None = None) -> None:
        self._frames = frames or []
        self.calls: list = []

    async def send(self, request):
        self.calls.append(request)
        for f in self._frames:
            yield AgentProtocolResponse(frames=[f], state_delta={}, next_action="continue")
        yield AgentProtocolResponse(frames=[], state_delta={}, next_action="complete")


class _ScriptedClient(SubAgentClient):
    """호출(attempt)마다 다르게 동작하는 fake — 복구 경로 검증용.

    behaviors[i] = "raise"          → send 이터레이션 시 예외 (→ relay E_RELAY)
                 | ErrorFrame        → 서브에이전트 자체 ErrorFrame 1개 방출
                 | list[frame]       → 정상 프레임 시퀀스
    마지막 behavior가 이후 모든 호출에 반복 적용된다.
    """

    def __init__(self, behaviors: list) -> None:
        self._behaviors = behaviors
        self.calls: list = []

    async def send(self, request):
        self.calls.append(request)
        b = self._behaviors[min(len(self.calls) - 1, len(self._behaviors) - 1)]
        if b == "raise":
            raise RuntimeError("connection refused")
            yield  # noqa: unreachable — async generator 표식
        if isinstance(b, ErrorFrame):
            yield AgentProtocolResponse(frames=[b], state_delta={}, next_action="complete")
            return
        for f in b:
            yield AgentProtocolResponse(frames=[f], state_delta={}, next_action="continue")
        yield AgentProtocolResponse(frames=[], state_delta={}, next_action="complete")


class _StateDeltaClient(SubAgentClient):
    """프레임 + state_delta를 반환하는 fake — state-mediated 핸드오프 검증용."""

    def __init__(self, frames: list, state_delta: dict) -> None:
        self._frames = frames
        self._delta = state_delta
        self.calls: list = []

    async def send(self, request):
        self.calls.append(request)
        for f in self._frames:
            yield AgentProtocolResponse(frames=[f], state_delta=self._delta, next_action="continue")
        yield AgentProtocolResponse(frames=[], state_delta={}, next_action="complete")


class _FakeIntent:
    def __init__(self, result: IntentResult | None) -> None:
        self._result = result

    async def analyze(self, messages, context):
        return self._result


def _intent(it: IntentType) -> IntentResult:
    return IntentResult(intent=it, confidence=0.9, analyzed_entities={})


def _draft_frame() -> WorkflowDraftFrame:
    return WorkflowDraftFrame(nodes=[], connections=[])


def _build(intent_result, *, composer=None, skills=None, personalization=None, llm=None):
    return LangGraphSupervisor(
        intent_analyzer=_FakeIntent(intent_result),
        personalization_client=personalization or _FakeClient(),
        composer_client=composer or _FakeClient(),
        skills_client=skills or _FakeClient(),
        llm=llm,
    )


async def _collect(sup, **kw):
    user_id, session_id = uuid4(), uuid4()
    return [f async for f in await sup.stream(user_id, session_id, kw.pop("msg", "hi"), **kw)]


def _actions(client: _FakeClient) -> list[str]:
    return [c.payload.get("action") for c in client.calls]


# ---------------------------------------------------------------- tests


class TestSupervisorLoop:
    @pytest.mark.asyncio
    async def test_session_frame_is_first(self):
        sup = _build(_intent(IntentType.CHITCHAT))
        frames = await _collect(sup)
        assert isinstance(frames[0], SessionFrame)

    @pytest.mark.asyncio
    async def test_chitchat_fast_path_no_relay(self):
        composer = _FakeClient()
        personalization = _FakeClient()
        sup = _build(_intent(IntentType.CHITCHAT), composer=composer, personalization=personalization)
        frames = await _collect(sup)

        # AgentNodeFrame 이름은 구체 intent(chitchat) — 단계 표시 보존
        node_frames = [f for f in frames if isinstance(f, AgentNodeFrame)]
        assert any(f.agent_node_name == "chitchat" for f in node_frames)
        assert [f for f in frames if isinstance(f, ResultFrame)]
        # fast-path는 composer relay 없음 + update_memory 없음 (relayed=False)
        assert composer.calls == []
        assert "update_memory" not in _actions(personalization)
        # load_memory는 bookend으로 호출됨
        assert "load_memory" in _actions(personalization)

    @pytest.mark.asyncio
    async def test_draft_routes_to_composer_with_transition_and_update_memory(self):
        composer = _FakeClient(frames=[_draft_frame(), ResultFrame(intent="propose", payload={})])
        personalization = _FakeClient()
        sup = _build(_intent(IntentType.DRAFT), composer=composer, personalization=personalization)
        frames = await _collect(sup, msg="슬랙 알림 보내줘")

        node_frames = [f for f in frames if isinstance(f, AgentNodeFrame)]
        assert any(f.agent_node_name == "composer" for f in node_frames)
        # transition 메시지가 relay 프레임 전에 yield
        chat = [f for f in frames if isinstance(f, ChatMessageFrame)]
        assert chat and "워크플로우 작성을 시작" in chat[0].content
        # relay 프레임 전파
        assert [f for f in frames if isinstance(f, WorkflowDraftFrame)]
        # composer 호출됨 + relay 후 update_memory bookend
        assert len(composer.calls) == 1
        assert "update_memory" in _actions(personalization)

    @pytest.mark.asyncio
    async def test_build_skill_routes_to_skills(self):
        skills = _FakeClient(frames=[ResultFrame(intent="build_skill", payload={})])
        composer = _FakeClient()
        sup = _build(_intent(IntentType.BUILD_SKILL), composer=composer, skills=skills)
        frames = await _collect(sup, msg="스킬 만들어줘")

        node_frames = [f for f in frames if isinstance(f, AgentNodeFrame)]
        assert any(f.agent_node_name == "build_skill" for f in node_frames)
        assert len(skills.calls) == 1
        assert composer.calls == []

    @pytest.mark.asyncio
    async def test_propose_finalize_no_relay(self):
        composer = _FakeClient()
        sup = _build(_intent(IntentType.PROPOSE), composer=composer)
        frames = await _collect(sup, msg="이대로 진행")

        node_frames = [f for f in frames if isinstance(f, AgentNodeFrame)]
        assert any(f.agent_node_name == "finalize" for f in node_frames)
        result = [f for f in frames if isinstance(f, ResultFrame)]
        assert result and result[0].intent == "propose"
        assert composer.calls == []

    @pytest.mark.asyncio
    async def test_unclassified_general_chat_no_llm(self):
        composer = _FakeClient()
        sup = _build(None, composer=composer, llm=None)  # intent None → general_chat
        frames = await _collect(sup, msg="음...")

        chat = [f for f in frames if isinstance(f, ChatMessageFrame)]
        assert chat  # 기본 안내 메시지
        # general_chat은 AgentNodeFrame 없음(단계 표시 제외) + relay 없음
        assert composer.calls == []


class TestSupervisorRecovery:
    """P2 복구 경로 — relay 실패 시 recovery_target 기반 재시도/보정.

    설계: docs/specs/plan/supervisor-loop-architecture.md §6.
    """

    @pytest.mark.asyncio
    async def test_connection_fail_then_succeed_suppresses_error(self):
        # 1차 연결 실패(E_RELAY, content 0) → 억제 후 재시도, 2차 성공
        composer = _ScriptedClient(
            ["raise", [_draft_frame(), ResultFrame(intent="propose", payload={})]]
        )
        sup = _build(_intent(IntentType.DRAFT), composer=composer)
        frames = await _collect(sup, msg="슬랙 알림 보내줘")

        # 억제 성공 — 사용자에게 ErrorFrame 미노출
        assert not [f for f in frames if isinstance(f, ErrorFrame)]
        # 정상 결과 프레임 전파
        assert [f for f in frames if isinstance(f, WorkflowDraftFrame)]
        # 1회 재시도로 총 2회 호출
        assert len(composer.calls) == 2
        # transition 안내는 1회만 (재시도 홉은 is_retry로 생략)
        transitions = [f for f in frames if isinstance(f, ChatMessageFrame) and "워크플로우 작성을 시작" in f.content]
        assert len(transitions) == 1

    @pytest.mark.asyncio
    async def test_connection_fail_twice_emits_error_once(self):
        # 두 번 다 실패 → 한도 초과 → 억제했던 ErrorFrame 한 번 노출
        composer = _ScriptedClient(["raise"])
        sup = _build(_intent(IntentType.DRAFT), composer=composer)
        frames = await _collect(sup, msg="슬랙 알림 보내줘")

        errors = [f for f in frames if isinstance(f, ErrorFrame)]
        assert len(errors) == 1
        assert errors[0].code == "E_RELAY"
        # 초기 + 재시도 1회 = 2회 호출 (MAX_RETRIES=1)
        assert len(composer.calls) == 2
        transitions = [f for f in frames if isinstance(f, ChatMessageFrame) and "워크플로우 작성을 시작" in f.content]
        assert len(transitions) == 1

    @pytest.mark.asyncio
    async def test_relay_limit_gives_up_without_retry(self):
        # content가 상한 초과 → E_RELAY_LIMIT(이미 노출) → 즉시 포기, 재시도 없음
        composer = _ScriptedClient([[_draft_frame(), _draft_frame(), _draft_frame()]])
        sup = _build(_intent(IntentType.DRAFT), composer=composer)
        sup._MAX_RELAY_FRAMES = 2  # 상한 강제
        frames = await _collect(sup, msg="슬랙 알림 보내줘")

        errors = [f for f in frames if isinstance(f, ErrorFrame)]
        assert any(e.code == "E_RELAY_LIMIT" for e in errors)
        # E_RELAY_LIMIT은 재시도 없음 — 1회 호출
        assert len(composer.calls) == 1

    @pytest.mark.asyncio
    async def test_subagent_error_routes_to_composer_correction(self):
        # skills가 자체 ErrorFrame 반환 → result_review → composer 보정 삽입
        skills = _ScriptedClient([ErrorFrame(code="E_SKILL", message="스킬 생성 실패")])
        composer = _FakeClient(frames=[_draft_frame(), ResultFrame(intent="propose", payload={})])
        sup = _build(_intent(IntentType.BUILD_SKILL), composer=composer, skills=skills)
        frames = await _collect(sup, msg="스킬 만들어줘")

        # 서브에이전트 자체 에러는 노출됨
        errors = [f for f in frames if isinstance(f, ErrorFrame)]
        assert any(e.code == "E_SKILL" for e in errors)
        # result_review → composer 보정 1회 실행
        assert len(composer.calls) == 1
        node_names = [f.agent_node_name for f in frames if isinstance(f, AgentNodeFrame)]
        assert "build_skill" in node_names and "composer" in node_names
        # 보정 후 정상 draft 프레임
        assert [f for f in frames if isinstance(f, WorkflowDraftFrame)]

    @pytest.mark.asyncio
    async def test_skill_then_compose_routes_both_hops_state_mediated(self):
        # P3 복합 — "스킬 만들어서 워크플로우" 한 발화가 SKILLS → COMPOSER 두 홉으로
        skills = _StateDeltaClient(
            frames=[ResultFrame(intent="build_skill", payload={})],
            state_delta={"selected_skill_id": "skill-123"},
        )
        composer = _FakeClient(frames=[_draft_frame(), ResultFrame(intent="propose", payload={})])
        sup = _build(_intent(IntentType.BUILD_SKILL), composer=composer, skills=skills)
        frames = await _collect(sup, msg="스킬 만들어서 워크플로우 만들어줘")

        # 두 홉 모두 디스패치, 순서 SKILLS(build_skill) → COMPOSER
        node_names = [f.agent_node_name for f in frames if isinstance(f, AgentNodeFrame)]
        assert node_names.index("build_skill") < node_names.index("composer")
        assert len(skills.calls) == 1
        assert len(composer.calls) == 1
        # state-mediated(§5): skills가 쓴 selected_skill_id를 composer가 payload로 수신
        assert composer.calls[0].payload.get("selected_skill_id") == "skill-123"
        assert [f for f in frames if isinstance(f, WorkflowDraftFrame)]

    @pytest.mark.asyncio
    async def test_subagent_error_correction_runs_only_once(self):
        # skills 에러 → composer 보정도 자체 에러 → review_inserted 가드로 무한루프 없음
        skills = _ScriptedClient([ErrorFrame(code="E_SKILL", message="실패")])
        composer = _ScriptedClient([ErrorFrame(code="E_COMPOSE", message="보정도 실패")])
        sup = _build(_intent(IntentType.BUILD_SKILL), composer=composer, skills=skills)
        frames = await _collect(sup, msg="스킬 만들어줘")

        # 보정 composer는 단 1회 (review_inserted 가드)
        assert len(composer.calls) == 1
        # 두 에러 모두 노출, 이후 종료
        codes = {f.code for f in frames if isinstance(f, ErrorFrame)}
        assert codes == {"E_SKILL", "E_COMPOSE"}


class TestSupervisorTwoShotResume:
    """P4 — round==2 특례 분기를 루프 resume 스텝으로 흡수.

    설계: docs/specs/plan/supervisor-loop-architecture.md §7.
    기존 동작 보존: composer 노드 표시 O / 진행 안내 X / load_memory·intent 재분석 X.
    """

    @pytest.mark.asyncio
    async def test_round2_resumes_composer_without_transition_or_intent(self):
        composer = _FakeClient(frames=[_draft_frame(), ResultFrame(intent="propose", payload={})])
        personalization = _FakeClient()
        sup = _build(
            _intent(IntentType.DRAFT), composer=composer, personalization=personalization
        )
        frames = await _collect(sup, msg="", round=2, selected_skill_id="skill-1")

        node_names = [f.agent_node_name for f in frames if isinstance(f, AgentNodeFrame)]
        # composer 단계 표시는 보존, 라우팅 노드(analyze_intent)는 없음
        assert "composer" in node_names
        assert "analyze_intent" not in node_names
        # resume 침묵 복귀 — 진행 안내 ChatMessageFrame 없음
        assert not any(
            isinstance(f, ChatMessageFrame) and "작성을 시작" in f.content for f in frames
        )
        # load_memory 생략, update_memory(bookend)는 수행
        actions = _actions(personalization)
        assert "load_memory" not in actions
        assert "update_memory" in actions
        # relay payload에 round/selected_skill_id 전파 (two-shot 핵심)
        assert composer.calls[0].payload.get("round") == 2
        assert composer.calls[0].payload.get("selected_skill_id") == "skill-1"
        # 정상 draft 프레임
        assert [f for f in frames if isinstance(f, WorkflowDraftFrame)]
