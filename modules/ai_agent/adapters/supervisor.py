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
from common_schemas.transport import (
    AgentNodeFrame,
    AnySSEFrame,
    ChatMessageFrame,
    ErrorFrame,
    PipelineStatusFrame,
    ResultFrame,
    SessionFrame,
    SSEFrame,
)

from ..domain.entities.session_ref import SessionRef
from ..domain.ports.llm_port import LLMPort
from ..domain.ports.session_frame_store import SessionFrameStore
from ..domain.ports.sub_agent_client import SubAgentClient
from ..domain.services.intent_analyzer_service import IntentAnalyzerService

_logger = logging.getLogger(__name__)

_FAST_INTENTS = {"chitchat", "info_question", "control", "workflow_execute"}
_COMPOSER_INTENTS = {"draft", "refine", "clarify"}


class _State(TypedDict):
    session_id: UUID
    user_id: UUID
    message: str
    trace_id: str | None
    turn_count: int
    personal_memory: list[MemoryEntry]
    intent: str | None
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
            "intent_analyzed_entities": {},
            "error": None,
            "round": round,
            "selected_skill_id": selected_skill_id,
        }

        all_frames: list[AnySSEFrame] = []

        try:
            # ── two-shot 2차 (REQ-013) — intent 재분석 없이 곧장 composer 재개 relay ──
            if round == 2:
                node_frame = AgentNodeFrame(agent_node_name="composer")
                all_frames.append(node_frame)
                yield node_frame
                async for frame in self._relay_stream(state, self._composer, AgentMode.WIZARD):
                    all_frames.append(frame)
                    yield frame
                await self._update_memory_node(state)
                if self._session_frame_store:
                    await self._save_session_frames(session_id, user_id, message, all_frames)
                return

            # ── load_memory ───────────────────────────────────────────────
            # supervisor 라우팅 노드는 사용자 단계 표시 대상 아님 — AgentNodeFrame yield 제외
            # (composer 노드 이후 늦게 도착 시 프론트 단계 역행 방지)
            all_frames.append(AgentNodeFrame(agent_node_name="load_memory"))

            mem_updates = await self._load_memory_node(state)
            state = {**state, **mem_updates}  # type: ignore[assignment]
            for frame in mem_updates.get("collected_frames", []):
                all_frames.append(frame)
                yield frame

            # ── analyze_intent ────────────────────────────────────────────
            intent_updates = await self._intent_node(state)
            state = {**state, **intent_updates}  # type: ignore[assignment]
            intent = state.get("intent")

            all_frames.append(AgentNodeFrame(agent_node_name="analyze_intent"))

            # ── route ─────────────────────────────────────────────────────
            if intent is None:
                chat_updates = await self._general_chat_node(state)
                for frame in chat_updates.get("collected_frames", []):
                    all_frames.append(frame)
                    yield frame

            elif intent in _FAST_INTENTS:
                node_frame = AgentNodeFrame(agent_node_name=intent)
                all_frames.append(node_frame)
                yield node_frame
                updates = await self._fast_response_node(state, intent)
                for frame in updates.get("collected_frames", []):
                    all_frames.append(frame)
                    yield frame

            elif intent == "propose":
                node_frame = AgentNodeFrame(agent_node_name="finalize")
                all_frames.append(node_frame)
                yield node_frame
                updates = await self._finalize_node(state)
                for frame in updates.get("collected_frames", []):
                    all_frames.append(frame)
                    yield frame

            elif intent == "build_skill":
                node_frame = AgentNodeFrame(agent_node_name="build_skill")
                all_frames.append(node_frame)
                yield node_frame
                transition = ChatMessageFrame(
                    role="assistant",
                    content="스킬 빌드를 시작할게요. 잠시만 기다려 주세요.",
                )
                all_frames.append(transition)
                yield transition
                async for frame in self._relay_stream(state, self._skills, AgentMode.SKILL_BUILDER):
                    all_frames.append(frame)
                    yield frame
                await self._update_memory_node(state)

            elif intent in _COMPOSER_INTENTS:
                node_frame = AgentNodeFrame(agent_node_name="composer")
                all_frames.append(node_frame)
                yield node_frame
                # transition을 relay 호출 전에 즉시 yield — 사용자 즉시 progress 인지
                transition = ChatMessageFrame(
                    role="assistant",
                    content="요청하신 워크플로우 작성을 시작할게요. 잠시만 기다려 주세요.",
                )
                all_frames.append(transition)
                yield transition
                # composer frame 수신 즉시 outer stream으로 pass-through
                async for frame in self._relay_stream(state, self._composer, AgentMode.WIZARD):
                    all_frames.append(frame)
                    yield frame
                await self._update_memory_node(state)

            else:
                _logger.warning("supervisor: 알 수 없는 intent=%s → 종료", intent)

        except Exception as exc:
            err_frame = ErrorFrame(code="E_SUPERVISOR", message=str(exc))
            all_frames.append(err_frame)
            yield err_frame

        if self._session_frame_store:
            await self._save_session_frames(session_id, user_id, message, all_frames)

    # ------------------------------------------------------------------ relay

    _MAX_RELAY_FRAMES = 200  # composer fixed DAG 예상 frame 수의 ~3배

    async def _relay_stream(
        self,
        state: _State,
        client: SubAgentClient,
        mode: AgentMode,
    ) -> AsyncGenerator[AnySSEFrame, None]:
        """composer/skills frame을 수신 즉시 outer stream으로 pass-through."""
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
            return {"intent": "clarify", "error": f"intent 분석 실패: {exc}"}
        if result is None:
            return {"intent": None, "intent_analyzed_entities": {}}
        return {
            "intent": result.intent,
            "intent_analyzed_entities": result.analyzed_entities,
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
