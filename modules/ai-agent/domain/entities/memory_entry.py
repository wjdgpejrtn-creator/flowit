from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal, Optional
from uuid import UUID, uuid4

from common_schemas.types import UtcDatetime
from pydantic import BaseModel, ConfigDict, Field


class MemoryEntry(BaseModel):
    model_config = ConfigDict(frozen=True)

    entry_id: UUID = Field(default_factory=uuid4)
    user_id: UUID
    memory_type: Literal["preference", "correction", "workflow_pattern", "summary"]
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    source_session_id: Optional[UUID] = None
    created_at: UtcDatetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def is_ephemeral(self) -> bool:
        return not self.content.strip()
