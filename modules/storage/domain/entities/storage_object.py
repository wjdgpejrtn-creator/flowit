from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from common_schemas.types import UtcDatetime
from pydantic import BaseModel, ConfigDict


class StorageObject(BaseModel):
    model_config = ConfigDict(frozen=True)

    object_id: UUID
    bucket: str
    key: str
    size: int
    content_type: str
    metadata: dict[str, str]
    uploaded_at: UtcDatetime
    expires_at: Optional[UtcDatetime] = None
    owner_id: Optional[UUID] = None
