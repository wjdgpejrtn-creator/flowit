from __future__ import annotations

from typing import AsyncGenerator
from uuid import UUID, uuid4

from common_schemas.transport import AgentNodeFrame, ResultFrame, SessionFrame, SSEFrame

from ...domain.ports.agent_memory_repository import AgentMemoryRepository
from ...domain.ports.llm_port import LLMPort


class ContinueConversationUseCase:
    def __init__(self, memory_repo: AgentMemoryRepository, llm: LLMPort) -> None:
        self._memory_repo = memory_repo
        self._llm = llm

    async def execute(
        self,
        session_id: UUID,
        message: str,
    ) -> AsyncGenerator[SSEFrame, None]:
        return self._stream(session_id, message)

    async def _stream(
        self,
        session_id: UUID,
        message: str,
    ) -> AsyncGenerator[SSEFrame, None]:
        yield SessionFrame(session_id=session_id, langgraph_thread_id=uuid4())

        memories = await self._memory_repo.find_by_session(session_id, limit=10)
        memory_context = "\n".join(f"- {m.content}" for m in memories)

        yield AgentNodeFrame(agent_node_name="context_node")

        prompt = f"User memories:\n{memory_context}\n\nUser message: {message}"
        response = await self._llm.generate(prompt)

        yield ResultFrame(intent="clarify", payload={"response": response})
