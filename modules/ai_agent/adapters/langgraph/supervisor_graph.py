"""LangGraph Supervisor Graph — Main Orchestrator 어댑터 레이어.

spec §3.1 supervisor diagram 구현. LangGraph는 adapters/에만 존재 (CLAUDE.md 제약).
6개 노드: load_memory → intent → [composer|skills|finalize] → update_memory → END
"""
from __future__ import annotations

import operator
from typing import Annotated, Any, AsyncGenerator, TypedDict
from uuid import UUID, uuid4

from langgraph.graph import END, StateGraph

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

from ...domain.ports.sub_agent_client import SubAgentClient
from ...domain.services.intent_analyzer_service import IntentAnalyzerService

_COMPOSER = "composer"
_SKILLS = "skills"
_FINALIZE = "finalize"


class _State(TypedDict):
    session_id: UUID
    user_id: UUID
    message: str
    trace_id: str | None
    personal_memory: list[MemoryEntry]
    intent: str | None
    intent_analyzed_entities: dict[str, Any]
    collected_frames: Annotated[list[AnySSEFrame], operator.add]
    error: str | None


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
    ) -> None:
        self._intent_analyzer = intent_analyzer
        self._personalization = personalization_client
        self._composer = composer_client
        self._skills = skills_client
        self._graph = self._build()

    # ------------------------------------------------------------------ public

    async def stream(
        self,
        user_id: UUID,
        session_id: UUID,
        message: str,
        trace_id: str | None = None,
    ) -> AsyncGenerator[SSEFrame, None]:
        return self._run(user_id, session_id, message, trace_id)

    async def _run(
        self,
        user_id: UUID,
        session_id: UUID,
        message: str,
        trace_id: str | None,
    ) -> AsyncGenerator[SSEFrame, None]:
        yield SessionFrame(session_id=session_id, langgraph_thread_id=uuid4())

        initial: _State = {
            "session_id": session_id,
            "user_id": user_id,
            "message": message,
            "trace_id": trace_id,
            "personal_memory": [],
            "intent": None,
            "intent_analyzed_entities": {},
            "collected_frames": [],
            "error": None,
        }

        async for event in self._graph.astream(initial, stream_mode="updates"):
            for node_name, updates in event.items():
                yield AgentNodeFrame(agent_node_name=node_name)
                for frame in updates.get("collected_frames", []):
                    yield frame
                if updates.get("error"):
                    yield ErrorFrame(code="E_SUPERVISOR", message=updates["error"])
                    return

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
            turn_count=1,
            mode=AgentMode.GENERAL,
            personal_memory=state["personal_memory"],
            execution_status=ExecutionStatus.RUNNING,
        )
        req = AgentProtocolRequest(
            session_id=state["session_id"],
            user_id=state["user_id"],
            state=agent_state,
            personal_memory=state["personal_memory"],
            payload={"action": "update_memory"},
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
            turn_count=1,
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
                frames.extend(resp.frames)
                if resp.next_action != "continue":
                    break
        except Exception as exc:
            return {"collected_frames": frames, "error": str(exc)}
        return {"collected_frames": frames}

    # ------------------------------------------------------------------ routing

    @staticmethod
    def _route(state: _State) -> str:
        intent = state.get("intent") or IntentType.CLARIFY
        if intent == IntentType.BUILD_SKILL:
            return _SKILLS
        if intent == IntentType.PROPOSE:
            return _FINALIZE
        return _COMPOSER  # draft / refine / clarify

    # ------------------------------------------------------------------ build

    def _build(self):
        graph: StateGraph = StateGraph(_State)

        graph.add_node("load_memory", self._load_memory_node)
        graph.add_node("intent", self._intent_node)
        graph.add_node(_COMPOSER, self._composer_node)
        graph.add_node(_SKILLS, self._skills_node)
        graph.add_node(_FINALIZE, self._finalize_node)
        graph.add_node("update_memory", self._update_memory_node)

        graph.set_entry_point("load_memory")
        graph.add_edge("load_memory", "intent")
        graph.add_conditional_edges(
            "intent",
            self._route,
            {_COMPOSER: _COMPOSER, _SKILLS: _SKILLS, _FINALIZE: _FINALIZE},
        )
        graph.add_edge(_COMPOSER, "update_memory")
        graph.add_edge(_SKILLS, "update_memory")
        graph.add_edge(_FINALIZE, "update_memory")
        graph.add_edge("update_memory", END)

        return graph.compile()
