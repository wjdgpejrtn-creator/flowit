from __future__ import annotations

from datetime import datetime
from typing import Optional

from common_schemas.types import UtcDatetime
from pydantic import BaseModel, ConfigDict


class ScanResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    clean: bool
    threat_name: Optional[str] = None
    scanned_at: UtcDatetime
