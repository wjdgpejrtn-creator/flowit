from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict


class RetentionPolicy(BaseModel):
    model_config = ConfigDict(frozen=True)

    ttl_days: Optional[int] = None
    archive_after_days: Optional[int] = None
