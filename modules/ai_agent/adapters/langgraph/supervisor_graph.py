"""LangGraph Supervisor Graph — Main Orchestrator 어댑터 레이어.

spec §3.1 supervisor diagram 구현. LangGraph는 adapters/에만 존재 (CLAUDE.md 제약).

결정론적 라우팅 구조:
  load_memory → agent_loop → END

  agent_loop: intent 분석 후 LLM 없이 결정론적 분기.
    chitchat/info_question/control/workflow_execute → 즉시 응답
    draft/refine/clarify → composer relay
    propose → finalize
    build_skill → skills relay
"""
from __future__ import annotations

import logging
import operator
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Annotated, Any, Literal, TypedDict
from uuid import UUID, uuid4

from pydantic import BaseModel

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
from langgraph.graph import END, StateGraph

from ...domain.entities.session_ref import SessionRef
from ...domain.ports.llm_port import LLMPort
from ...domain.ports.session_frame_store import SessionFrameStore
from ...domain.ports.sub_agent_client import SubAgentClient
from ...domain.services.intent_analyzer_service import IntentAnalyzerService

_logger = logging.getLogger(__name__)

_MAX_SUPERVISOR_ITERATIONS = 5


class _State(TypedDict):
    session_id: UUID
    user_id: UUID
    message: str
    trace_id: str | None
    turn_count: int
    personal_memory: list[MemoryEntry]
    intent: str | None
    intent_analyzed_entities: dict[str, Any]
    collected_frames: Annotated[list[AnySSEFrame], operator.add]
    error: str | None
    agent_done: bool
    agent_iterations: int
    composer_done: bool  # composer/skills 호출 완료 여부 — update_memory 단계 진입 트리거


class LangGraphSupervisor:
    """Main Orchestrator LangGraph supervisor — sub-agent HTTP 라우팅.

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
        self._graph = self._build()

    # ------------------------------------------------------------------ public

    async def stream(
        self,
        user_id: UUID,
        session_id: UUID,
        message: str,
        trace_id: str | None = None,
        turn_count: int = 1,
    ) -> AsyncGenerator[SSEFrame, None]:
        return self._run(user_id, session_id, message, trace_id, turn_count)

    async def _run(
        self,
        user_id: UUID,
        session_id: UUID,
        message: str,
        trace_id: str | None,
        turn_count: int = 1,
    ) -> AsyncGenerator[SSEFrame, None]:
        yield SessionFrame(session_id=session_id, langgraph_thread_id=uuid4())

        initial: _State = {
            "session_id": session_id,
            "user_id": user_id,
            "message": message,
            "trace_id": trace_id,
            "turn_count": turn_count,
            "personal_memory": [],
            "intent": None,
            "intent_analyzed_entities": {},
            "collected_frames": [],
            "error": None,
            "agent_done": False,
            "agent_iterations": 0,
            "composer_done": False,
        }

        all_frames: list[AnySSEFrame] = []
        try:
            async for event in self._graph.astream(initial, stream_mode="updates"):
                for node_name, updates in event.items():
                    if node_name != "agent":
                        node_frame = AgentNodeFrame(agent_node_name=node_name)
                        all_frames.append(node_frame)
                        yield node_frame
                    if not isinstance(updates, dict):
                        continue
                    for frame in updates.get("collected_frames", []):
                        all_frames.append(frame)
                        yield frame
                    if updates.get("error"):
                        err_frame = ErrorFrame(code="E_SUPERVISOR", message=updates["error"])
                        all_frames.append(err_frame)
                        yield err_frame
                        return
        except Exception as exc:
            err_frame = ErrorFrame(code="E_SUPERVISOR", message=str(exc))
            all_frames.append(err_frame)
            yield err_frame

        if self._session_frame_store:
            await self._save_session_frames(session_id, user_id, message, all_frames)

    # ------------------------------------------------------------------ agent loop

    def _build_supervisor_prompt(self, state: _State) -> str:
        intent = state.get("intent") or "아직 분석 안 됨"
        return (
            "Main Orchestrator AI 에이전트입니다.\n\n"
            f"사용자 메시지: {state['message'][:300]}\n"
            f"현재 의도: {intent}\n\n"
            "사용 가능한 툴:\n"
            "- analyze_intent: 사용자 의도 분석 (draft/refine/clarify/propose/build_skill)\n"
            "- call_composer: Workflow Composer sub-agent 호출 (draft/refine/clarify 의도)\n"
            "- call_skills_builder: Skills Builder sub-agent 호출 (build_skill 의도)\n"
            "- finalize: 워크플로우 제안 확정 (propose 의도)\n"
            "- update_memory: Personalization 메모리 업데이트 (작업 완료 후)\n"
            "- done: 모든 작업 완료\n\n"
            "다음에 실행할 툴 하나를 선택하고 이유를 설명하세요.\n"
            '{"tool_name": "<툴이름>", "reasoning": "<이유>"}'
        )

    async def _agent_node(self, state: _State) -> dict:
        if self._llm is None:
            return {"error": "LLM 미주입 — tool-calling 불가", "agent_done": True}

        iterations = state.get("agent_iterations", 0) + 1
        if iterations > _MAX_SUPERVISOR_ITERATIONS:
            return {
                "agent_done": True,
                "error": f"슈퍼바이저 최대 반복 횟수({_MAX_SUPERVISOR_ITERATIONS}) 초과",
                "agent_iterations": iterations,
            }

        intent = state.get("intent")

        # ── 1단계: intent 미분석 → analyze_intent ──────────────────────────────
        if intent is None:
            _logger.info("supervisor: intent 없음 → analyze_intent 강제 실행")
            updates = await self._intent_node(state)
            intent = updates.get("intent")
            _logger.info("supervisor: intent 분석 결과 = %s", intent)

            # 미분류(None) → general_chat으로 즉시 자연어 응답
            if intent is None:
                chat_updates = await self._general_chat_node(state)
                return {
                    **chat_updates,
                    "agent_iterations": iterations,
                    "agent_done": True,
                    "collected_frames": [AgentNodeFrame(agent_node_name="analyze_intent")]
                    + chat_updates.get("collected_frames", []),
                }

            return {
                **updates,
                "agent_iterations": iterations,
                "collected_frames": [AgentNodeFrame(agent_node_name="analyze_intent")]
                + updates.get("collected_frames", []),
            }

        # ── 2단계: 결정론적 라우팅 ──────────────────────────────────────────────
        _FAST_INTENTS = {"chitchat", "info_question", "control", "workflow_execute"}
        _COMPOSER_INTENTS = {"draft", "refine", "clarify"}

        # fast-path: composer 없이 즉시 응답
        if intent in _FAST_INTENTS:
            _logger.info("supervisor: fast-path 처리 intent=%s", intent)
            updates = await self._fast_response_node(state, intent)
            return {
                **updates,
                "agent_iterations": iterations,
                "agent_done": True,
                "collected_frames": [AgentNodeFrame(agent_node_name=intent)]
                + updates.get("collected_frames", []),
            }

        # propose → finalize
        if intent == "propose":
            updates = await self._finalize_node(state)
            return {
                **updates,
                "agent_iterations": iterations,
                "agent_done": True,
                "collected_frames": [AgentNodeFrame(agent_node_name="finalize")]
                + updates.get("collected_frames", []),
            }

        # build_skill → 트랜지션 메시지 + skills_builder relay
        if intent == "build_skill":
            if state.get("composer_done"):
                await self._update_memory_node(state)
                return {"agent_iterations": iterations, "agent_done": True}
            transition = ChatMessageFrame(
                role="assistant",
                content="스킬 빌드를 시작할게요. 잠시만 기다려 주세요.",
            )
            updates = await self._skills_node(state)
            return {
                **updates,
                "agent_iterations": iterations,
                "composer_done": True,
                "collected_frames": [transition] + updates.get("collected_frames", []),
            }

        # draft/refine/clarify → 트랜지션 메시지 + composer relay
        if intent in _COMPOSER_INTENTS:
            if state.get("composer_done"):
                await self._update_memory_node(state)
                return {"agent_iterations": iterations, "agent_done": True}
            transition = ChatMessageFrame(
                role="assistant",
                content="요청하신 워크플로우 작성을 시작할게요. 잠시만 기다려 주세요.",
            )
            updates = await self._composer_node(state)
            return {
                **updates,
                "agent_iterations": iterations,
                "composer_done": True,
                "collected_frames": [transition] + updates.get("collected_frames", []),
            }

        # unknown intent fallback → done
        _logger.warning("supervisor: 알 수 없는 intent=%s → 종료", intent)
        return {"agent_done": True, "agent_iterations": iterations}

    async def _fast_response_node(self, state: _State, intent: str) -> dict:
        """fast-path 응답 노드 — LLM 0~1 call로 즉시 처리."""
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

        # chitchat / info_question → 즉시 응답 (LLM cold start 방지)
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

    @staticmethod
    def _route_agent(state: _State) -> str:
        if state.get("agent_done") or state.get("error"):
            return "end"
        return "continue"

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
        # result가 None이면 미분류 → intent=None 유지 (general_chat으로 분기)
        if result is None:
            return {"intent": None, "intent_analyzed_entities": {}}
        return {
            "intent": result.intent,
            "intent_analyzed_entities": result.analyzed_entities,
        }

    async def _composer_node(self, state: _State) -> dict:
        return await self._relay(state, self._composer, AgentMode.WIZARD)

    async def _skills_node(self, state: _State) -> dict:
        return await self._relay(state, self._skills, AgentMode.SKILL_BUILDER)

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
        except Exception:
            pass  # memory update 실패는 non-fatal
        return {}

    # ------------------------------------------------------------------ helpers

    async def _relay(
        self,
        state: _State,
        client: SubAgentClient,
        mode: AgentMode,
    ) -> dict:
        agent_state = AgentState(
            session_id=state["session_id"],
            user_id=state["user_id"],
            messages=[{"role": "user", "content": state["message"]}],
            turn_count=state["turn_count"],
            mode=mode,
            personal_memory=state["personal_memory"],
            execution_status=ExecutionStatus.RUNNING,
        )
        req = AgentProtocolRequest(
            session_id=state["session_id"],
            user_id=state["user_id"],
            state=agent_state,
            personal_memory=state["personal_memory"],
            payload={"message": state["message"]},
            trace_id=state["trace_id"],
        )
        frames: list[AnySSEFrame] = []
        try:
            async for resp in client.send(req):
                for frame in resp.frames:
                    frames.append(frame)
                if resp.next_action != "continue":
                    break
        except Exception as exc:
            return {"collected_frames": frames, "error": str(exc)}
        return {"collected_frames": frames}

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

    # ------------------------------------------------------------------ build

    def _build(self):
        graph: StateGraph = StateGraph(_State)

        # tool-calling 구조: load_memory → agent_loop
        graph.add_node("load_memory", self._load_memory_node)
        graph.add_node("agent", self._agent_node)

        graph.set_entry_point("load_memory")
        graph.add_edge("load_memory", "agent")
        graph.add_conditional_edges(
            "agent",
            self._route_agent,
            {"continue": "agent", "end": END},
        )

        return graph.compile()
