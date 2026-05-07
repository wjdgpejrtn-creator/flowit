from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class MemoryEntry(BaseModel):
    model_config = ConfigDict(frozen=True)

    entry_id: UUID = Field(default_factory=uuid4)
    user_id: UUID
    memory_type: Literal["preference", "correction", "workflow_pattern", "summary"]
    content: str
    source_session_id: UUID
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def is_ephemeral(self) -> bool:
        """일회성 잡담은 저장하지 않는다. content가 비어있으면 저장 대상 아님."""
        return not self.content.strip()
