"""Personalization — 세션 시작 시 사용자 memory 로드.

Orchestrator가 세션 시작 시 호출해 AgentState.personal_memory에 주입.
"""
from __future__ import annotations

from uuid import UUID

from common_schemas import MemoryEntry, MemoryType

from ....domain.entities.memory_file import MemoryFile
from ....domain.ports.personal_memory_store import PersonalMemoryStore

_MD_TYPE_TO_MEMORY_TYPE: dict[str, MemoryType] = {
    "user": "preference",
    "feedback": "correction",
    "project": "workflow_pattern",
    "reference": "summary",
}


def _to_memory_entry(user_id: UUID, file: MemoryFile) -> MemoryEntry:
    memory_type: MemoryType = _MD_TYPE_TO_MEMORY_TYPE.get(file.memory_type, "summary")
    return MemoryEntry(
        user_id=user_id,
        memory_type=memory_type,
        content=file.body,
        metadata={"filename": file.filename, "name": file.name, "description": file.description},
    )


class LoadUserMemoryUseCase:
    """GCS MEMORY.md 인덱스 → 개별 .md 파일 로드 → MemoryEntry 목록 반환.

    파일 로드 실패(FileNotFoundError)는 무시하고 로드 가능한 항목만 반환한다.
    """

    def __init__(self, memory_store: PersonalMemoryStore) -> None:
        self._store = memory_store

    async def execute(self, user_id: UUID) -> list[MemoryEntry]:
        refs = await self._store.load_index(user_id)
        entries: list[MemoryEntry] = []
        for ref in refs:
            try:
                file = await self._store.load_file(user_id, ref.filename)
                entries.append(_to_memory_entry(user_id, file))
            except FileNotFoundError:
                pass
        return entries
