"""Main Orchestrator — sub-agent 라우팅 use case.

흐름 (spec §3.1 supervisor diagram):
    세션 시작
      → load_memory_node      (HTTP → agent-personalization: LoadUserMemoryUseCase)
      → intent_node           (IntentAnalyzerService)
      → 분기:
          intent=draft/refine/clarify → composer_node       (HTTP → agent-composer)
          intent=build_skill          → skills_node          (HTTP → agent-skills-builder)
          intent=propose              → finalize_node
      → update_memory_node    (HTTP → agent-personalization: UpdateUserMemoryUseCase, propose 제외)
      → [finally] cleanup     (HTTP → agent-personalization: {"action": "cleanup"})
"""
from __future__ import annotations

from typing import AsyncGenerator, AsyncIterator
from uuid import UUID, uuid4

from common_schemas.agent import AgentState, MemoryEntry
from common_schemas.agent_protocol import AgentProtocolRequest, AgentProtocolResponse
from common_schemas.enums import AgentMode, ExecutionStatus
from common_schemas.transport import (
    AgentNodeFrame,
    ErrorFrame,
    ResultFrame,
    SessionFrame,
    SSEFrame,
)

from ....domain.ports.sub_agent_client import SubAgentClient
from ....domain.services.intent_analyzer_service import IntentAnalyzerService


class RouteRequestUseCase:
    """LangGraph supervisor 패턴으로 sub-agent를 라우팅하는 main orchestrator."""

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

    async def execute(
        self,
        user_id: UUID,
        session_id: UUID,
        message: str,
        trace_id: str | None = None,
    ) -> AsyncGenerator[SSEFrame, None]:
        return self._stream(user_id, session_id, message, trace_id)

    async def _stream(
        self,
        user_id: UUID,
        session_id: UUID,
        message: str,
        trace_id: str | None,
    ) -> AsyncGenerator[SSEFrame, None]:
        yield SessionFrame(session_id=session_id, langgraph_thread_id=uuid4())

        stub_state = AgentState(
            session_id=session_id,
            user_id=user_id,
            messages=[],
            turn_count=0,
            mode=AgentMode.GENERAL,
            execution_status=ExecutionStatus.RUNNING,
        )
        state = stub_state
        turn_count = 0

        try:
            # 1. load_memory_node
            yield AgentNodeFrame(agent_node_name="load_memory_node")
            personal_memory = await self._load_personal_memory(stub_state, trace_id)

            # 2. intent_node
            yield AgentNodeFrame(agent_node_name="intent_node")
            messages = [{"role": "user", "content": message}]
            turn_count += 1
            try:
                intent = await self._intent_analyzer.analyze(messages, context={})
            except Exception as exc:
                yield ErrorFrame(code="E_INTENT_ANALYZE", message=str(exc))
                return

            # 3. routable state
            mode = (
                AgentMode.SKILL_BUILDER
                if intent.intent == "build_skill"
                else AgentMode.WIZARD
            )
            state = AgentState(
                session_id=session_id,
                user_id=user_id,
                messages=messages,
                turn_count=turn_count,
                mode=mode,
                intent_result=intent,
                personal_memory=personal_memory,
                execution_status=ExecutionStatus.RUNNING,
            )

            # 4. route
            if intent.intent in ("draft", "refine", "clarify"):
                yield AgentNodeFrame(agent_node_name="composer_node")
                async for frame in self._relay(
                    self._composer, state, {"message": message}, trace_id
                ):
                    yield frame

            elif intent.intent == "build_skill":
                yield AgentNodeFrame(agent_node_name="skills_node")
                skill_payload = self._build_skill_payload(intent.analyzed_entities, message, user_id)
                async for frame in self._relay(
                    self._skills, state, skill_payload, trace_id
                ):
                    yield frame

            elif intent.intent == "propose":
                yield AgentNodeFrame(agent_node_name="finalize_node")
                yield ResultFrame(
                    intent="propose",
                    payload={"session_id": str(session_id), "status": "accepted"},
                )

            # 5. update_memory_node — propose는 메모리 저장 불필요
            if intent.intent in ("draft", "refine", "clarify", "build_skill"):
                yield AgentNodeFrame(agent_node_name="update_memory_node")
                await self._update_personal_memory(state, turn_count, trace_id)

        finally:
            await self._cleanup_personal_memory(state, trace_id)

    # ------------------------------------------------------------------ helpers

    async def _load_personal_memory(
        self,
        state: AgentState,
        trace_id: str | None,
    ) -> list[MemoryEntry]:
        req = AgentProtocolRequest(
            session_id=state.session_id,
            user_id=state.user_id,
            state=state,
            payload={"action": "load_memory"},
            trace_id=trace_id,
        )
        memories: list[MemoryEntry] = []
        async for resp in self._personalization.send(req):
            raw = resp.state_delta.get("personal_memory", [])
            if raw:
                memories = [MemoryEntry.model_validate(m) for m in raw]
            if resp.next_action != "continue":
                break
        return memories

    async def _update_personal_memory(
        self,
        state: AgentState,
        turn_count: int,
        trace_id: str | None,
    ) -> None:
        req = AgentProtocolRequest(
            session_id=state.session_id,
            user_id=state.user_id,
            state=state,
            personal_memory=list(state.personal_memory),
            payload={
                "action": "update_memory",
                "turn_count": turn_count,
                "session_summary": None,
                "workflow": None,
            },
            trace_id=trace_id,
        )
        async for resp in self._personalization.send(req):
            if resp.next_action != "continue":
                break

    async def _cleanup_personal_memory(
        self,
        state: AgentState,
        trace_id: str | None,
    ) -> None:
        req = AgentProtocolRequest(
            session_id=state.session_id,
            user_id=state.user_id,
            state=state,
            payload={"action": "cleanup"},
            trace_id=trace_id,
        )
        try:
            async for resp in self._personalization.send(req):
                if resp.next_action != "continue":
                    break
        except Exception:
            pass  # cleanup은 non-fatal

    def _build_skill_payload(
        self,
        entities: dict,
        message: str,
        user_id: UUID,
    ) -> dict:
        source_type = entities.get("source_type", "sop")
        payload: dict = {"source_type": source_type}
        if source_type == "industry_default":
            payload["industry_code"] = entities.get("industry_code", "")
        elif source_type == "functional_domain":
            payload["domain_code"] = entities.get("domain_code", "")
        else:  # sop
            payload["document"] = {
                "document_id": str(uuid4()),
                "user_id": str(user_id),
                "file_meta": {
                    "file_name": "user_input.txt",
                    "file_type": "txt",
                    "mime_type": "text/plain",
                    "file_size": len(message.encode("utf-8")),
                },
                "blocks": [
                    {
                        "block_id": str(uuid4()),
                        "block_type": "text",
                        "content": message,
                    }
                ],
            }
        return payload

    async def _relay(
        self,
        client: SubAgentClient,
        state: AgentState,
        payload: dict,
        trace_id: str | None,
    ) -> AsyncGenerator[SSEFrame, None]:
        req = AgentProtocolRequest(
            session_id=state.session_id,
            user_id=state.user_id,
            state=state,
            personal_memory=list(state.personal_memory),
            payload=payload,
            trace_id=trace_id,
        )
        async for resp in client.send(req):
            for frame in resp.frames:
                yield frame
            if resp.next_action != "continue":
                break
