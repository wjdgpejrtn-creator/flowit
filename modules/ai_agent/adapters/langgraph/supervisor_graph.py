"""LangGraph Supervisor Graph — Main Orchestrator 어댑터 레이어.

spec §3.1 supervisor diagram 구현. LangGraph는 adapters/에만 존재 (CLAUDE.md 제약).

Tool-calling 에이전트 구조:
  load_memory (전처리, 항상 실행) → agent_loop → END

  agent_loop: LLM이 아래 툴 중 하나를 선택해 실행, done 반환 시 종료.
    analyze_intent / call_composer / call_skills_builder / finalize /
    update_memory / done
"""
from __future__ import annotations

import asyncio
import logging
import operator
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Annotated, Any, Literal, TypedDict
from uuid import UUID, uuid4

from pydantic import BaseModel

from common_schemas.agent import AgentState, MemoryEntry
from common_schemas.agent_protocol import AgentProtocolRequest
from common_schemas.enums import AgentMode, ExecutionStatus, IntentType
from common_schemas.transport import (
    AgentNodeFrame,
    AnySSEFrame,
    ErrorFrame,
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

_COMPOSER = "composer"
_SKILLS = "skills"
_FINALIZE = "finalize"
_MAX_SUPERVISOR_ITERATIONS = 10

_RELAY_TOOLS = {"call_composer", "call_skills_builder"}


class _SupervisorAction(BaseModel):
    """LLM 슈퍼바이저가 다음에 실행할 툴을 선택하는 스키마."""

    tool_name: Literal[
        "analyze_intent",
        "call_composer",
        "call_skills_builder",
        "finalize",
        "update_memory",
        "done",
    ]
    reasoning: str


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
        self._live_queues: dict[UUID, asyncio.Queue] = {}
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
        queue: asyncio.Queue[SSEFrame | None] = asyncio.Queue()
        self._live_queues[session_id] = queue

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
        }

        async def _run_graph() -> None:
            try:
                async for event in self._graph.astream(initial, stream_mode="updates"):
                    for node_name, updates in event.items():
                        # agent 루프 노드는 내부에서 툴별 AgentNodeFrame을 emit
                        if node_name != "agent":
                            await queue.put(AgentNodeFrame(agent_node_name=node_name))
                        if not isinstance(updates, dict):
                            continue
                        # relay 툴(call_composer/call_skills_builder)은 _relay()에서 직접 queue에 put
                        for frame in updates.get("collected_frames", []):
                            await queue.put(frame)
                        if updates.get("error"):
                            await queue.put(
                                ErrorFrame(code="E_SUPERVISOR", message=updates["error"])
                            )
                            return
            finally:
                await queue.put(None)
                self._live_queues.pop(session_id, None)

        asyncio.create_task(_run_graph())

        all_frames: list[AnySSEFrame] = []
        while True:
            frame = await queue.get()
            if frame is None:
                break
            all_frames.append(frame)
            yield frame

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

        try:
            action = await self._llm.generate_structured(
                self._build_supervisor_prompt(state), _SupervisorAction
            )
        except Exception as exc:
            return {"error": f"툴 선택 실패: {exc}", "agent_done": True, "agent_iterations": iterations}

        _logger.info("supervisor 툴 선택: %s — %s", action.tool_name, action.reasoning)

        tool_map = {
            "analyze_intent":      self._intent_node,
            "call_composer":       self._composer_node,
            "call_skills_builder": self._skills_node,
            "finalize":            self._finalize_node,
            "update_memory":       self._update_memory_node,
        }

        if action.tool_name == "done":
            return {"agent_done": True, "agent_iterations": iterations}

        tool_fn = tool_map.get(action.tool_name)
        if tool_fn is None:
            return {
                "error": f"알 수 없는 툴: {action.tool_name}",
                "agent_done": True,
                "agent_iterations": iterations,
            }

        try:
            updates = await tool_fn(state)
        except Exception as exc:
            return {
                "error": f"툴 실행 실패({action.tool_name}): {exc}",
                "agent_done": True,
                "agent_iterations": iterations,
            }

        tool_frames = updates.get("collected_frames", [])
        pre_frames: list[AnySSEFrame] = [AgentNodeFrame(agent_node_name=action.tool_name)]

        return {
            **updates,
            "agent_iterations": iterations,
            "collected_frames": pre_frames + tool_frames,
        }

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
            return {"personal_memory": [], "error": f"load_memory 실패: {exc}"}
        return {"personal_memory": memories}

    async def _intent_node(self, state: _State) -> dict:
        try:
            result = await self._intent_analyzer.analyze(
                [{"role": "user", "content": state["message"]}], context={}
            )
        except Exception as exc:
            return {"intent": "clarify", "error": f"intent 분석 실패: {exc}"}
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
        live_queue = self._live_queues.get(state["session_id"])
        frames: list[AnySSEFrame] = []
        try:
            async for resp in client.send(req):
                for frame in resp.frames:
                    frames.append(frame)
                    if live_queue:
                        await live_queue.put(frame)
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
