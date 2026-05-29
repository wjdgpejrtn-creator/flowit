from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from common_schemas.transport import AgentNodeFrame, ResultFrame, SessionFrame

from ai_agent.application.agents.workflow_composer import ContinueConversationUseCase
from ai_agent.domain.entities import MemoryEntry
from ai_agent.domain.ports import AgentMemoryRepository, LLMPort


def _build_uc(memories=None, llm_response="응답"):
    repo = AsyncMock(spec=AgentMemoryRepository)
    repo.find_by_session = AsyncMock(return_value=memories or [])
    llm = AsyncMock(spec=LLMPort)
    llm.generate = AsyncMock(return_value=llm_response)
    return ContinueConversationUseCase(memory_repo=repo, llm=llm), repo, llm


class TestContinueConversationUseCase:
    @pytest.mark.asyncio
    async def test_yields_session_and_result_frames(self):
        uc, _, _ = _build_uc()
        gen = await uc.execute(uuid4(), "슬랙 보내줘")
        frames = [f async for f in gen]

        assert any(isinstance(f, SessionFrame) for f in frames)
        assert any(isinstance(f, ResultFrame) for f in frames)
        # M2: langgraph_thread_id 생성 여부 확인
        session = next(f for f in frames if isinstance(f, SessionFrame))
        assert session.langgraph_thread_id is not None

    @pytest.mark.asyncio
    async def test_yields_agent_node_frame(self):
        uc, _, _ = _build_uc()
        gen = await uc.execute(uuid4(), "계속 진행해줘")
        frames = [f async for f in gen]

        # M1: agent_node_name 값 검증
        node_frame = next(f for f in frames if isinstance(f, AgentNodeFrame))
        assert node_frame.agent_node_name == "context_node"

    @pytest.mark.asyncio
    async def test_result_frame_contains_llm_response(self):
        uc, _, _ = _build_uc(llm_response="완료했습니다")
        gen = await uc.execute(uuid4(), "뭔가 해줘")
        frames = [f async for f in gen]

        result = next(f for f in frames if isinstance(f, ResultFrame))
        # H1: intent 값 명시 검증
        assert result.intent == "continue"
        assert result.payload["response"] == "완료했습니다"

    @pytest.mark.asyncio
    async def test_frame_emission_order(self):
        # H2: SSE 프레임 방출 순서 검증
        uc, _, _ = _build_uc()
        gen = await uc.execute(uuid4(), "테스트")
        frames = [f async for f in gen]

        assert isinstance(frames[0], SessionFrame)
        assert isinstance(frames[1], AgentNodeFrame)
        assert isinstance(frames[2], ResultFrame)

    @pytest.mark.asyncio
    async def test_memory_fetched_with_session_id(self):
        session_id = uuid4()
        uc, repo, _ = _build_uc()
        gen = await uc.execute(session_id, "테스트")
        [f async for f in gen]

        repo.find_by_session.assert_called_once_with(session_id, limit=10)

    @pytest.mark.asyncio
    async def test_memory_content_included_in_prompt(self):
        user_id = uuid4()
        memories = [
            MemoryEntry(user_id=user_id, memory_type="preference", content="슬랙 선호"),
            MemoryEntry(user_id=user_id, memory_type="summary", content="이전 요약"),
        ]
        uc, _, llm = _build_uc(memories=memories)
        gen = await uc.execute(uuid4(), "계속 진행해줘")
        [f async for f in gen]

        prompt = llm.generate.call_args[0][0]
        assert "슬랙 선호" in prompt
        assert "이전 요약" in prompt

    @pytest.mark.asyncio
    async def test_empty_memory_still_generates_response(self):
        uc, _, llm = _build_uc(memories=[])
        gen = await uc.execute(uuid4(), "처음 말하는 거야")
        frames = [f async for f in gen]

        llm.generate.assert_called_once()
        assert any(isinstance(f, ResultFrame) for f in frames)
