from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from common_schemas.exceptions import ExecutionError

from ..entities.memory_entry import MemoryEntry
from ..ports.llm_port import LLMPort

_SYSTEM_PROMPT = """You are a session memory summarizer.
Given the conversation, extract memories worth keeping long-term.
Only extract non-trivial preferences, workflow patterns, or corrections.
Do NOT store one-off small talk.

Respond with a JSON array:
[{"memory_type": "<preference|correction|workflow_pattern|summary>", "content": "<string>"}]
If nothing is worth keeping, return [].
"""


class MemorySummarizer:
    def __init__(self, llm: LLMPort) -> None:
        self._llm = llm

    async def summarize(
        self,
        user_id: UUID,
        session_id: UUID,
        messages: list[dict[str, Any]],
    ) -> list[MemoryEntry]:
        prompt_messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(messages, ensure_ascii=False)},
        ]
        response = await self._llm.generate(prompt_messages)
        return self._parse(response, user_id, session_id)

    def _parse(
        self,
        response: dict[str, Any],
        user_id: UUID,
        session_id: UUID,
    ) -> list[MemoryEntry]:
        try:
            items = json.loads(response["content"])
            entries = []
            for item in items:
                entry = MemoryEntry(
                    user_id=user_id,
                    memory_type=item["memory_type"],
                    content=item["content"],
                    source_session_id=session_id,
                )
                if not entry.is_ephemeral():
                    entries.append(entry)
            return entries
        except Exception as e:
            raise ExecutionError(f"MemoryEntry 파싱 실패: {e}", code="E_MEMORY_PARSE")
