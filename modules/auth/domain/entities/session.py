from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class Session(BaseModel):
    model_config = ConfigDict(frozen=True)

    session_id: UUID
    user_id: UUID
    session_hash: str
    expires_at: datetime
    is_revoked: bool = False
    created_at: datetime

    def is_valid(self) -> bool:
        return not self.is_revoked and datetime.now(timezone.utc) < self.expires_at
