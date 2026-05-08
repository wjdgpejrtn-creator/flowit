from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal, Optional

from common_schemas.types import UtcDatetime
from pydantic import BaseModel, ConfigDict, Field


class ConversationMessage(BaseModel):
    model_config = ConfigDict(frozen=True)

    role: Literal["user", "assistant", "system"]
    content: str
    timestamp: UtcDatetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Optional[dict[str, Any]] = None
