from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from ai_agent.application.agents.personalization import SaveMemoryUseCase
from ai_agent.domain.entities import MemoryEntry
from ai_agent.domain.ports import AgentMemoryRepository


class TestSaveMemoryUseCase:
    @pytest.mark.asyncio
    async def test_saves_non_ephemeral_entries(self):
        repo = AsyncMock(spec=AgentMemoryRepository)
        repo.save = AsyncMock()
        uc = SaveMemoryUseCase(repo)
        sid = uuid4()
        entries = [
            MemoryEntry(user_id=uuid4(), memory_type="preference", content="슬랙 선호"),
            MemoryEntry(user_id=uuid4(), memory_type="summary", content="   "),
        ]
        await uc.execute(sid, entries)
        assert repo.save.call_count == 1

    @pytest.mark.asyncio
    async def test_skips_ephemeral_entries(self):
        repo = AsyncMock(spec=AgentMemoryRepository)
        repo.save = AsyncMock()
        uc = SaveMemoryUseCase(repo)
        entries = [MemoryEntry(user_id=uuid4(), memory_type="summary", content="  ")]
        await uc.execute(uuid4(), entries)
        repo.save.assert_not_called()
