from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class CorrectionPattern(BaseModel):
    model_config = ConfigDict(frozen=True)

    pattern_id: UUID = Field(default_factory=uuid4)
    user_id: UUID
    original: str
    corrected: str
    frequency: int = 1
    last_seen_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def is_recurring(self) -> bool:
        """2회 이상 반복된 교정 패턴인지 확인."""
        return self.frequency >= 2
