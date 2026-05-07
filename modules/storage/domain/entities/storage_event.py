from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class StorageEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    event_type: Literal["uploaded", "downloaded", "deleted", "expired"]
    object_id: UUID
    timestamp: datetime
    actor_id: Optional[UUID] = None
