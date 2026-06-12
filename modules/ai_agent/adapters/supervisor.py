"""Supervisor Graph — Main Orchestrator 어댑터 레이어.

spec §3.1 supervisor diagram 구현.

결정론적 라우팅 구조:
  load_memory → analyze_intent → route → END

  route: intent 분석 후 결정론적 분기.
    chitchat/info_question/control/workflow_execute → 즉시 응답
    draft/refine/clarify → transition 즉시 yield + composer relay stream
    propose → finalize
    build_skill → transition 즉시 yield + skills relay stream
    None → general_chat (LLM 자연어 응답)
"""
from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any, TypedDict
from uuid import UUID, uuid4

from common_schemas.agent import AgentState, MemoryEntry
from common_schemas.agent_protocol import AgentProtocolRequest
from common_schemas.enums import AgentMode, ExecutionStatus
from common_schemas.handoff import HandoffPayload
from common_schemas.transport import (
    AgentNodeFrame,
    AnySSEFrame,
    ChatMessageFrame,
    ErrorFrame,
    PipelineStatusFrame,
    ResultFrame,
    SessionFrame,
    SkillBuilderWizardFrame,
    SSEFrame,
)

from ..domain.entities.session_ref import SessionRef
from ..domain.ports.llm_port import LLMPort
from ..domain.ports.session_frame_store import SessionFrameStore
from ..domain.ports.sub_agent_client import SubAgentClient
from ..domain.services.intent_analyzer_service import IntentAnalyzerService, classify_recipe
from ..domain.services.supervisor_router import MAX_HOPS, make_plan, recovery_target, route
from ..domain.value_objects.route_plan import RoutePlan, RouteTarget

# two-shot 2차 resume 전용 plan 라벨 (intent 미분류, 단일 composer 스텝).
_RESUME_RECIPE = "__two_shot_resume__"

_logger = logging.getLogger(__name__)

# 단일 의도는 1-스텝 레시피라 라우팅 분기는 RECIPES(supervisor_router)로 이관.
# 복합 의도(skill_then_compose)는 P3에서 intent 분류기가 키를 산출하면 자동 활성.
_COMPOSER_TARGETS = {RouteTarget.COMPOSER, RouteTarget.SKILLS}  # relay 후 update_memory 필요

# relay 래퍼가 생성하는 실패 코드. 이 외 ErrorFrame은 서브에이전트 자체 에러로 보고
# result_review 경로(composer 보정)로 라우팅한다 (설계서 §6).
_RELAY_FAIL_CODES = {"E_RELAY", "E_RELAY_LIMIT"}


class _State(TypedDict):
    session_id: UUID
    user_id: UUID
    message: str
    trace_id: str | None
    turn_count: int
    personal_memory: list[MemoryEntry]
    intent: str | None
    recipe_key: str | None  # 라우팅 키 (단일 의도=intent값 / 복합=화이트리스트 키)
    intent_analyzed_entities: dict[str, Any]
    error: str | None
    # two-shot HITL relay passthrough (REQ-013)
    round: int
    selected_skill_id: str | None


class LangGraphSupervisor:
    """Main Orchestrator supervisor — sub-agent HTTP 라우팅.

    spec §3.1. services/agents/orchestrator/main.py composition root에서 인스턴스화.
    """

    def __init__(
        self,
        intent_analyzer: IntentAnalyzerService,
        personalization_client: SubAgentClient,
        composer_client: SubAgentClient,
        skills_client: SubAgentClient,
        session_frame_store: SessionFrameStore | None = None,
        llm: LLMPort | None = None,
    ) -> None:
        self._intent_analyzer = intent_analyzer
        self._personalization = personalization_client
        self._composer = composer_client
        self._skills = skills_client
        self._session_frame_store = session_frame_store
        self._llm = llm

    # ------------------------------------------------------------------ public

    async def stream(
        self,
        user_id: UUID,
        session_id: UUID,
        message: str,
        trace_id: str | None = None,
        turn_count: int = 1,
        round: int = 1,
        selected_skill_id: str | None = None,
    ) -> AsyncGenerator[SSEFrame, None]:
        return self._run(user_id, session_id, message, trace_id, turn_count, round, selected_skill_id)

    async def _run(
        self,
        user_id: UUID,
        session_id: UUID,
        message: str,
        trace_id: str | None,
        turn_count: int = 1,
        round: int = 1,
        selected_skill_id: str | None = None,
    ) -> AsyncGenerator[SSEFrame, None]:
        yield SessionFrame(session_id=session_id, langgraph_thread_id=uuid4())

        state: _State = {
            "session_id": session_id,
            "user_id": user_id,
            "message": message,
            "trace_id": trace_id,
            "turn_count": turn_count,
            "personal_memory": [],
            "intent": None,
            "recipe_key": None,
            "intent_analyzed_entities": {},
            "error": None,
            "round": round,
            "selected_skill_id": selected_skill_id,
        }

        all_frames: list[AnySSEFrame] = []

        try:
            if round == 2:
                # ── two-shot 2차 resume (REQ-013) ──────────────────────────
                # intent 재분석/load_memory 없이 composer 스텝부터 재개. 별도 가로채기
                # 대신 단일 스텝 plan으로 동일 루프를 태운다 (설계서 §7). resume 플래그가
                # transition 안내를 억제해 기존 동작(AgentNodeFrame만, 안내 없음)을 보존.
                plan = RoutePlan(recipe_key=_RESUME_RECIPE, steps=[RouteTarget.COMPOSER])
                intent = None
                resume = True
            else:
                # ── load_memory ───────────────────────────────────────────
                # supervisor 라우팅 노드는 사용자 단계 표시 대상 아님 — AgentNodeFrame yield 제외
                # (composer 노드 이후 늦게 도착 시 프론트 단계 역행 방지)
                all_frames.append(AgentNodeFrame(agent_node_name="load_memory"))

                mem_updates = await self._load_memory_node(state)
                state = {**state, **mem_updates}  # type: ignore[assignment]
                for frame in mem_updates.get("collected_frames", []):
                    all_frames.append(frame)
                    yield frame

                # ── analyze_intent ────────────────────────────────────────
                intent_updates = await self._intent_node(state)
                state = {**state, **intent_updates}  # type: ignore[assignment]
                intent = state.get("intent")

                all_frames.append(AgentNodeFrame(agent_node_name="analyze_intent"))

                # 라우팅은 recipe_key(복합 포함)로, 노드 동작 표시는 intent로 분리.
                plan = make_plan(state.get("recipe_key"))
                resume = False

            # ── supervisor 제어 루프 ───────────────────────────────────────
            # intent → 레시피(forward 스텝 큐). 단일 의도는 1-스텝이라 동작은
            # 기존 1-홉 디스패처와 동일. 복합 레시피(skill_then_compose)는 한
            # 루프에서 여러 hop을 순차 디스패치한다 (state-mediated, 설계서 §2·§5).
            #
            # 복구 경로(설계서 §6): relay 실패를 recovery_target(순수 함수)로 판정한다.
            #   · 연결 실패(E_RELAY, content 0) → 첫 ErrorFrame 억제 후 동일 target 재시도
            #   · E_RELAY_LIMIT / content 후 실패 → 이미 노출됨 → 즉시 포기
            #   · 서브에이전트 자체 ErrorFrame → result_review → composer 보정 1회
            # 3중 무한루프 방어: MAX_HOPS(전체 홉) · retry_count(MAX_RETRIES) · review_inserted.
            # plan/intent/resume은 위 round 분기에서 이미 셋업됨 (round==2=단일 composer resume).
            relayed = False
            retry_count = 0       # 동일 target 연결 재시도 누적 (recovery_mode)
            review_inserted = False  # result_review composer 보정 1회 가드
            hops = 0
            while hops < MAX_HOPS:
                target = route(plan)
                if target is RouteTarget.DONE:
                    break
                # 재시도 홉은 transition(AgentNodeFrame/안내)을 다시 내지 않는다 (중복 방지).
                is_retry = retry_count > 0
                # SKILLS 홉: 뒤에 COMPOSER가 이어지면(복합 skill_then_compose) 서브에이전트 relay,
                # 단독이면 프론트 위저드 트리거만(REQ-010). plan.remaining()은 현재 커서(SKILLS)부터.
                skills_relay = RouteTarget.COMPOSER in plan.remaining()
                outcome: dict[str, Any] = {}
                async for frame in self._dispatch(
                    target, state, intent, outcome, is_retry=is_retry, resume=resume,
                    skills_relay=skills_relay,
                ):
                    all_frames.append(frame)
                    yield frame
                resume = False  # resume 억제는 재개 첫 홉에만 적용
                if target in _COMPOSER_TARGETS:
                    relayed = True
                hops += 1

                if not outcome.get("failed"):
                    # state-mediated 핸드오프(§5): SKILLS가 산출한 selected_skill_id를
                    # state에 누적 → 다음 COMPOSER 홉 relay가 read (직접 통신 없음).
                    sid = (outcome.get("state_delta") or {}).get("selected_skill_id")
                    if sid:
                        state = {**state, "selected_skill_id": sid}  # type: ignore[assignment]
                    retry_count = 0
                    plan.advance()
                    continue

                # ── 실패 처리 — recovery_target로 결정 ──
                held = outcome.get("suppressed_error")
                if held is not None:
                    # content 0 E_RELAY — 억제됨 → recovery_mode 재시도 후보
                    handoff = self._make_handoff("recovery_mode", outcome)
                    if recovery_target(plan, handoff, retry_count) is None:
                        all_frames.append(held)  # 포기 — 억제했던 에러 노출
                        yield held
                        break
                    retry_count += 1
                    continue  # advance 안 함 → 동일 target 재시도
                # 에러는 이미 노출된 상태
                if outcome.get("error_code") in _RELAY_FAIL_CODES:
                    break  # E_RELAY_LIMIT / content 후 E_RELAY — 즉시 포기
                # SKILLS 자체 에러는 composer 보정 대상 아님 — 스킬 빌드 실패는 즉시 종료(REQ-010).
                # 복합 skill_then_compose에서 skills가 실패하면 그 스킬로 compose해도 의미가 없다.
                if target is RouteTarget.SKILLS:
                    break
                # 서브에이전트 자체 ErrorFrame → result_review → composer 보정 (1회)
                if review_inserted:
                    break
                handoff = self._make_handoff("result_review", outcome)
                rt = recovery_target(plan, handoff, retry_count)
                if rt is None:
                    break
                plan.advance()       # 실패한 스텝 통과
                plan.insert(rt)      # 그 자리에 composer 보정 삽입
                review_inserted = True
                retry_count = 0
                continue
            else:
                _logger.warning("supervisor: 홉 상한(%d) 도달 — 루프 강제 종료", MAX_HOPS)

            # ── update_memory (relay가 있었던 경우만) ──────────────────────
            if relayed:
                await self._update_memory_node(state)

        except Exception as exc:
            err_frame = ErrorFrame(code="E_SUPERVISOR", message=str(exc))
            all_frames.append(err_frame)
            yield err_frame

        if self._session_frame_store:
            await self._save_session_frames(session_id, user_id, message, all_frames)

    # ------------------------------------------------------------------ dispatch

    async def _dispatch(
        self,
        target: RouteTarget,
        state: _State,
        intent: str | None,
        outcome: dict[str, Any],
        is_retry: bool = False,
        resume: bool = False,
        skills_relay: bool = True,
    ) -> AsyncGenerator[AnySSEFrame, None]:
        """한 홉의 target을 디스패치 — 산출 프레임을 모두 yield (호출부가 append+yield).

        load_memory/update_memory는 루프 북엔드(호출부)에서 처리하므로 여기 없다.
        프레임 시퀀스는 승격 전 1-홉 디스패처와 동일하게 보존한다.

        relay target(COMPOSER/SKILLS)의 실패는 ``outcome``(가변 dict)에 기록한다 —
        ``failed``/``error_code``/``suppressed_error``. 로컬 노드는 자체 try/except로
        항상 프레임을 내므로 실패를 기록하지 않는다. ``is_retry``면 transition
        (AgentNodeFrame/안내 메시지)을 생략해 재시도 시 중복 노출을 막는다.
        ``resume``(two-shot 2차)면 AgentNodeFrame은 내되 안내 메시지만 생략한다 —
        사용자는 1차에 이미 진행 안내를 받았으므로 재개 시 침묵 복귀가 옳다.
        """
        if target is RouteTarget.GENERAL_CHAT:
            updates = await self._general_chat_node(state)
            for frame in updates.get("collected_frames", []):
                yield frame

        elif target is RouteTarget.FAST_RESPONSE:
            # AgentNodeFrame 이름은 구체 intent(chitchat/control/…) — 프론트 단계 표시 보존
            yield AgentNodeFrame(agent_node_name=intent or "fast_response")
            updates = await self._fast_response_node(state, intent or "")
            for frame in updates.get("collected_frames", []):
                yield frame

        elif target is RouteTarget.FINALIZE:
            yield AgentNodeFrame(agent_node_name="finalize")
            updates = await self._finalize_node(state)
            for frame in updates.get("collected_frames", []):
                yield frame

        elif target is RouteTarget.SKILLS:
            if not is_retry:
                yield AgentNodeFrame(agent_node_name="build_skill")
            # 단일 build_skill(skills_relay=False, 후속 COMPOSER 없음)은 프론트 위저드를 띄우는
            # 트리거만 발행하고 서브에이전트 relay를 생략한다 — 실제 빌드(추출·생성·게시)는 프론트
            # REST(skillApi)가 자가구동한다(REQ-010 통합). outcome은 비워둬 성공으로 advance.
            # 복합 skill_then_compose(skills_relay=True)는 기존 relay 유지 — COMPOSER가 산출된
            # selected_skill_id를 state-mediated로 소비해야 하므로 서브에이전트가 실제로 빌드한다.
            if not skills_relay:
                if not resume:
                    yield ChatMessageFrame(
                        role="assistant",
                        content="스킬 빌더를 열었어요. 어떤 재료로 만들지 골라주세요.",
                    )
                yield SkillBuilderWizardFrame()
                return
            if not is_retry and not resume:
                # transition을 relay 호출 전에 즉시 yield — 사용자 즉시 progress 인지
                yield ChatMessageFrame(
                    role="assistant",
                    content="스킬 빌드를 시작할게요. 잠시만 기다려 주세요.",
                )
            async for frame in self._relay_monitored(state, self._skills, AgentMode.SKILL_BUILDER, outcome):
                yield frame

        elif target is RouteTarget.COMPOSER:
            if not is_retry:
                yield AgentNodeFrame(agent_node_name="composer")
                if not resume:
                    yield ChatMessageFrame(
                        role="assistant",
                        content="요청하신 워크플로우 작성을 시작할게요. 잠시만 기다려 주세요.",
                    )
            async for frame in self._relay_monitored(state, self._composer, AgentMode.WIZARD, outcome):
                yield frame

        else:
            _logger.warning("supervisor: 디스패치 불가 target=%s → 무시", target)

    # ------------------------------------------------------------------ relay

    _MAX_RELAY_FRAMES = 200  # composer fixed DAG 예상 frame 수의 ~3배

    async def _relay_stream(
        self,
        state: _State,
        client: SubAgentClient,
        mode: AgentMode,
        state_delta_sink: dict[str, Any] | None = None,
    ) -> AsyncGenerator[AnySSEFrame, None]:
        """composer/skills frame을 수신 즉시 outer stream으로 pass-through.

        ``state_delta_sink``가 주어지면 서브에이전트가 반환한 state_delta를 누적해
        호출부가 state-mediated 핸드오프(예: selected_skill_id)를 읽게 한다 (§5).
        """
        agent_state = AgentState(
            session_id=state["session_id"],
            user_id=state["user_id"],
            messages=[{"role": "user", "content": state["message"]}],
            turn_count=state["turn_count"],
            mode=mode,
            personal_memory=state["personal_memory"],
            execution_status=ExecutionStatus.RUNNING,
        )
        # two-shot 라운드/선택 스킬을 payload로 passthrough (1차는 round=1·None 기본 → 무영향)
        payload: dict[str, Any] = {
            "message": state["message"],
            "round": state.get("round", 1),
        }
        selected = state.get("selected_skill_id")
        if selected:
            payload["selected_skill_id"] = selected
        req = AgentProtocolRequest(
            session_id=state["session_id"],
            user_id=state["user_id"],
            state=agent_state,
            personal_memory=state["personal_memory"],
            payload=payload,
            trace_id=state["trace_id"],
        )
        try:
            count = 0
            async for resp in client.send(req):
                if state_delta_sink is not None and resp.state_delta:
                    state_delta_sink.update(resp.state_delta)
                for frame in resp.frames:
                    count += 1
                    if count > self._MAX_RELAY_FRAMES:
                        yield ErrorFrame(code="E_RELAY_LIMIT", message=f"relay frame 수 상한({self._MAX_RELAY_FRAMES}) 초과")
                        return
                    yield frame
                if resp.next_action != "continue":
                    break
        except Exception as exc:
            yield ErrorFrame(code="E_RELAY", message=str(exc))

    async def _relay_monitored(
        self,
        state: _State,
        client: SubAgentClient,
        mode: AgentMode,
        outcome: dict[str, Any],
    ) -> AsyncGenerator[AnySSEFrame, None]:
        """``_relay_stream`` 위 실패 감지 래퍼 (복구 루프 입력, 설계서 §6).

        ErrorFrame을 만나면 ``outcome``에 실패를 기록한다. 단 **content 0 상태의
        E_RELAY**(사전 연결 실패)는 yield를 보류(``suppressed_error``)해, 호출부가
        재시도로 무에러 결과를 대체하거나 포기 시에만 노출하도록 한다. content가
        이미 나간 뒤의 실패나 서브에이전트 자체 ErrorFrame은 그대로 노출한다.
        """
        content = 0
        sink = outcome.setdefault("state_delta", {})
        async for frame in self._relay_stream(state, client, mode, state_delta_sink=sink):
            if isinstance(frame, ErrorFrame):
                outcome["failed"] = True
                outcome["error_code"] = frame.code
                outcome["error_message"] = frame.message
                if frame.code == "E_RELAY" and content == 0:
                    # 사전 연결 실패 — 보류해 재시도 시 대체 가능
                    outcome["suppressed_error"] = frame
                    return
                yield frame  # E_RELAY_LIMIT / content 후 실패 / 서브에이전트 자체 에러
                return
            content += 1
            yield frame
        outcome["content_count"] = content

    @staticmethod
    def _make_handoff(handoff_type: str, outcome: dict[str, Any]) -> HandoffPayload:
        """실패 outcome → 복구 핸드오프 계약 (recovery_target 입력)."""
        code = outcome.get("error_code")
        msg = outcome.get("error_message")
        return HandoffPayload(
            handoff_type=handoff_type,  # type: ignore[arg-type]
            direction="reverse",
            error_codes=[code] if code else [],
            error_messages=[msg] if msg else [],
            state_data={},
            correlation_id=uuid4(),
        )

    # ------------------------------------------------------------------ nodes

    async def _load_memory_node(self, state: _State) -> dict:
        stub = AgentState(
            session_id=state["session_id"],
            user_id=state["user_id"],
            messages=[],
            turn_count=0,
            mode=AgentMode.GENERAL,
            execution_status=ExecutionStatus.RUNNING,
        )
        req = AgentProtocolRequest(
            session_id=state["session_id"],
            user_id=state["user_id"],
            state=stub,
            payload={"action": "load_memory"},
            trace_id=state["trace_id"],
        )
        memories: list[MemoryEntry] = []
        try:
            async for resp in self._personalization.send(req):
                raw = resp.state_delta.get("personal_memory", [])
                if raw:
                    memories = [MemoryEntry.model_validate(m) for m in raw]
                if resp.next_action != "continue":
                    break
        except Exception as exc:
            _logger.warning("load_memory 실패 (non-fatal, 빈 메모리로 계속): %s", exc)
            return {
                "personal_memory": [],
                "collected_frames": [
                    PipelineStatusFrame(service_name="load_memory", status="failed", elapsed_ms=0)
                ],
            }
        return {"personal_memory": memories}

    async def _intent_node(self, state: _State) -> dict:
        try:
            result = await self._intent_analyzer.analyze(
                [{"role": "user", "content": state["message"]}], context={}
            )
        except Exception as exc:
            return {"intent": "clarify", "recipe_key": "clarify", "error": f"intent 분석 실패: {exc}"}
        intent = result.intent if result is not None else None
        # intent = 노드 동작용(fast_response 분기·단계 표시), recipe_key = 라우팅용.
        # 복합 발화(skill_then_compose)는 base intent(BUILD_SKILL)와 별도 키를 가진다.
        recipe_key = classify_recipe(state["message"], intent)
        return {
            "intent": intent,
            "recipe_key": recipe_key,
            "intent_analyzed_entities": result.analyzed_entities if result is not None else {},
        }

    async def _fast_response_node(self, state: _State, intent: str) -> dict:
        """fast-path 응답 노드 — LLM 0 call로 즉시 처리."""
        msg = state["message"]

        if intent == "control":
            if any(k in msg for k in ["취소", "초기화", "리셋", "reset", "처음"]):
                text = "알겠습니다. 대화를 초기화했습니다. 새로운 워크플로우를 말씀해 주세요."
            elif any(k in msg for k in ["중단", "멈춰", "stop"]):
                text = "작업을 중단했습니다."
            else:
                text = "명령을 처리했습니다."
            return {"collected_frames": [ResultFrame(intent="chitchat", payload={"message": text})]}

        if intent == "workflow_execute":
            return {
                "collected_frames": [
                    ResultFrame(
                        intent="propose",
                        payload={"message": "워크플로우를 실행하려면 채팅창의 '▶ 실행' 버튼을 클릭하세요.", "status": "info"},
                    )
                ]
            }

        if intent == "info_question":
            text = (
                "저는 업무 자동화 워크플로우를 만들어 드리는 AI 어시스턴트예요. "
                "예) '매주 월요일 보고서를 Slack으로 보내줘', '구글 시트 데이터 요약해서 이메일 발송' 등을 말씀해 주세요!"
            )
        else:
            text = "안녕하세요! 어떤 업무를 자동화하고 싶으신가요? 워크플로우를 만들어 드릴게요 😊"
        return {"collected_frames": [ResultFrame(intent="chitchat", payload={"message": text})]}

    async def _general_chat_node(self, state: _State) -> dict:
        """미분류 입력 — LLM으로 자연어 응답 생성 (2~3문장, 워크플로우로 자연스럽게 유도)."""
        if self._llm is None:
            text = "안녕하세요! 어떤 업무를 자동화하고 싶으신가요?"
            return {"collected_frames": [ChatMessageFrame(role="assistant", content=text)]}
        system = (
            "당신은 업무 자동화 워크플로우를 만들어주는 AI 어시스턴트입니다. "
            "사용자가 자연스러운 대화를 시작했습니다. 친근하고 짧게 응답하고, "
            "어떤 업무를 자동화하고 싶은지 자연스럽게 유도하세요. 2~3문장 이내로 한국어로 답하세요."
        )
        try:
            text = await self._llm.generate(f"{system}\n\n사용자: {state['message']}")
        except Exception as exc:
            _logger.warning("general_chat LLM 실패, 기본 응답 사용: %s", exc)
            text = "안녕하세요! 어떤 업무를 자동화하고 싶으신가요? 말씀해 주시면 워크플로우를 만들어 드릴게요."
        return {"collected_frames": [ChatMessageFrame(role="assistant", content=text)]}

    async def _finalize_node(self, state: _State) -> dict:
        return {
            "collected_frames": [
                ResultFrame(
                    intent="propose",
                    payload={"session_id": str(state["session_id"]), "status": "accepted"},
                )
            ]
        }

    async def _update_memory_node(self, state: _State) -> dict:
        agent_state = AgentState(
            session_id=state["session_id"],
            user_id=state["user_id"],
            messages=[{"role": "user", "content": state["message"]}],
            turn_count=state["turn_count"],
            mode=AgentMode.GENERAL,
            personal_memory=state["personal_memory"],
            execution_status=ExecutionStatus.RUNNING,
        )
        req = AgentProtocolRequest(
            session_id=state["session_id"],
            user_id=state["user_id"],
            state=agent_state,
            personal_memory=state["personal_memory"],
            payload={
                "action": "update_memory",
                "turn_count": state["turn_count"],
                "session_summary": None,
                "workflow": None,
            },
            trace_id=state["trace_id"],
        )
        try:
            async for resp in self._personalization.send(req):
                if resp.next_action != "continue":
                    break
        except Exception as exc:
            _logger.warning("update_memory 실패 (non-fatal): %s", exc)
        return {}

    # ------------------------------------------------------------------ helpers

    async def _save_session_frames(
        self,
        session_id: UUID,
        user_id: UUID,
        message: str,
        frames: list[SSEFrame],
    ) -> None:
        try:
            workflow_id: UUID | None = None
            for frame in frames:
                if isinstance(frame, ResultFrame):
                    wf_str = frame.payload.get("workflow_id")
                    if wf_str:
                        try:
                            workflow_id = UUID(wf_str)
                        except Exception:
                            pass
                    break
            ref = SessionRef(
                session_id=session_id,
                user_id=user_id,
                workflow_id=workflow_id,
                created_at=datetime.now(UTC),
                message_preview=message[:100],
            )
            await self._session_frame_store.save_session(ref, frames)  # type: ignore[union-attr]
        except Exception as exc:
            _logger.warning("session frame 저장 실패 (non-fatal): %s", exc)
