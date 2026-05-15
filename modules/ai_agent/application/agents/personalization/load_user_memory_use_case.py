"""Personalization — 세션 시작 시 사용자 memory 로드.

GCS PersonalSkill → MemoryEntry 변환 후 Orchestrator AgentState에 주입.
skill_type → memory_type 매핑:
    user       → preference
    feedback   → correction
    project    → workflow_pattern
    reference  → summary
"""
from __future__ import annotations

from uuid import UUID

from common_schemas import MemoryEntry, MemoryType

from ai_agent.domain.entities.personal_skill import PersonalSkill
from ai_agent.domain.ports.personal_memory_store import PersonalMemoryStore

_SKILL_TO_MEMORY_TYPE: dict[str, MemoryType] = {
    "user": "preference",
    "feedback": "correction",
    "project": "workflow_pattern",
    "reference": "summary",
}


class LoadUserMemoryUseCase:
    def __init__(self, memory_store: PersonalMemoryStore) -> None:
        self._store = memory_store

    async def execute(self, user_id: UUID) -> list[MemoryEntry]:
        skills = await self._store.list_entries(user_id)
        return [_to_memory_entry(skill) for skill in skills]


def _to_memory_entry(skill: PersonalSkill) -> MemoryEntry:
    content = f"## {skill.name}\n{skill.description}\n\n{skill.body}".strip()
    return MemoryEntry(
        user_id=skill.user_id,
        memory_type=_SKILL_TO_MEMORY_TYPE[skill.skill_type],
        content=content,
        metadata={
            "skill_name": skill.name,
            "skill_type": skill.skill_type,
            "updated_at": skill.updated_at.isoformat(),
        },
    )
