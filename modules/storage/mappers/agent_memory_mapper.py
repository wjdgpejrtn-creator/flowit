from __future__ import annotations

from ai_agent.domain.entities.memory_entry import MemoryEntry

from ..orm.agent_memory_model import AgentMemoryModel


class AgentMemoryMapper:
    @staticmethod
    def to_domain(orm: AgentMemoryModel) -> MemoryEntry:
        return MemoryEntry(
            entry_id=orm.entry_id,
            user_id=orm.user_id,
            memory_type=orm.memory_type,
            content=orm.content,
            source_session_id=orm.source_session_id,
            metadata=orm.metadata_json,
            created_at=orm.created_at,
        )

    @staticmethod
    def to_orm(entity: MemoryEntry) -> AgentMemoryModel:
        return AgentMemoryModel(
            entry_id=entity.entry_id,
            user_id=entity.user_id,
            memory_type=entity.memory_type,
            content=entity.content,
            source_session_id=entity.source_session_id,
            metadata_json=entity.metadata,
            created_at=entity.created_at,
        )
